// MDC Automation API (Cloudflare Worker)
//   POST /api/generate   { widthIn, depthIn, heightIn, typeName }  -> { jobId, resultKey }
//   GET  /api/status?id=<jobId>&key=<resultKey>                     -> { status, downloadUrl? }
// APS credentials stay here on the server; the browser never sees them.
// Generate is protected by: optional access key, per-visitor rate limit, and Cloudflare Turnstile.
// Status needs the unguessable job id + result key returned by generate.

const APS = "https://developer.api.autodesk.com";
const DA = `${APS}/da/us-east/v3`;
const TEMPLATE_KEY = "templates/generic-model.rft";
// results/<uuid>__<friendly name>.rfa  (the friendly name becomes the download file name)
const RESULT_KEY_PATTERN = /^results\/[0-9a-f-]{36}__[A-Za-z0-9._-]{1,120}\.rfa$/;

let cachedToken = null; // { value, expiresAt } per Worker isolate

export default {
  async fetch(request, env) {
    const cors = {
      "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-MDC-Key",
    };
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });

    const json = (body, status = 200) =>
      new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

    const url = new URL(request.url);
    try {
      if (request.method === "POST" && url.pathname === "/api/generate") {
        // 1. Access key (on while REQUIRE_ACCESS_KEY is "true" in wrangler.toml)
        if (env.REQUIRE_ACCESS_KEY !== "false" &&
            (!env.ACCESS_KEY || request.headers.get("X-MDC-Key") !== env.ACCESS_KEY))
          return json({ error: "Access key is missing or incorrect." }, 401);

        // 2. Rate limit per visitor
        const ip = request.headers.get("CF-Connecting-IP") || "unknown";
        if (env.GENERATE_LIMITER) {
          const { success } = await env.GENERATE_LIMITER.limit({ key: ip });
          if (!success) return json({ error: "Too many requests. Please wait a minute and try again." }, 429);
        }

        // 3. Human check (Cloudflare Turnstile)
        const input = await request.json().catch(() => ({}));
        if (!(await verifyTurnstile(input.turnstileToken, ip, env)))
          return json({ error: "The human check did not pass. Please try again." }, 403);

        return json(await generate(input, env), 202);
      }
      if (request.method === "GET" && url.pathname === "/api/status") return json(await status(url, env));
      return json({ error: "Not found." }, 404);
    } catch (err) {
      console.error(err);
      return json({ error: err.publicMessage || "The request could not be completed." }, err.httpStatus || 500);
    }
  },
};

async function generate(input, env) {
  const params = {
    widthIn: dim(input.widthIn, "Width"),
    depthIn: dim(input.depthIn, "Depth"),
    heightIn: dim(input.heightIn, "Height"),
    typeName: String(input.typeName || "Standard").replace(/[^A-Za-z0-9 _-]/g, "").trim().slice(0, 60) || "Standard",
  };

  const token = await getToken(env);
  const resultKey = `results/${crypto.randomUUID()}__${friendlyName(params)}.rfa`;
  const oss = (key) => `urn:adsk.objects:os.object:${env.APS_BUCKET}/${key}`;
  const auth = { Authorization: `Bearer ${token}` };

  const wi = await apsJson(token, "POST", `${DA}/workitems`, {
    activityId: `${env.APS_NICKNAME}.MDCBoxFamily+prod`,
    limitProcessingTimeSec: 120, // safety net: stop any single job after 2 minutes
    arguments: {
      template: { url: oss(TEMPLATE_KEY), headers: auth },
      params: { url: "data:application/json," + JSON.stringify(params) },
      result: { verb: "put", url: oss(resultKey), headers: auth },
    },
  });

  return { jobId: wi.id, resultKey, params };
}

async function status(url, env) {
  const id = url.searchParams.get("id") || "";
  const key = url.searchParams.get("key") || "";
  if (!/^[0-9a-f]{32}$/i.test(id) || !RESULT_KEY_PATTERN.test(key)) throw fail(400, "Invalid job reference.");

  const token = await getToken(env);
  const wi = await apsJson(token, "GET", `${DA}/workitems/${id}`);

  if (wi.status !== "success") {
    if (!["pending", "inprogress"].includes(wi.status)) console.log(`Job ${id} ended as ${wi.status}: ${wi.reportUrl}`);
    return { status: wi.status };
  }

  const fileName = key.split("__")[1];
  const base = `${APS}/oss/v2/buckets/${env.APS_BUCKET}/objects/${encodeURIComponent(key)}/signeds3download?minutesExpiration=30`;
  const disposition = encodeURIComponent(`attachment; filename="${fileName}"`);

  // Ask Autodesk to serve the file with the friendly name; fall back to a plain link if that option is refused.
  let dl;
  try {
    dl = await apsJson(token, "GET", `${base}&response-content-disposition=${disposition}`);
  } catch (err) {
    console.log("Named download link refused, using plain link: " + err.message);
    dl = await apsJson(token, "GET", base);
  }
  return { status: "success", downloadUrl: dl.url, fileName };
}

// "Equipment Box", 24 x 18 x 60  ->  MDC-Equipment-Box-24x18x60
function friendlyName(p) {
  const n = (v) => String(Number(v)); // 24 -> "24", 24.5 -> "24.5", 30 -> "30"
  const type = p.typeName.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "Box";
  return `MDC-${type}-${n(p.widthIn)}x${n(p.depthIn)}x${n(p.heightIn)}`;
}

async function verifyTurnstile(token, ip, env) {
  if (!env.TURNSTILE_SECRET) throw fail(500, "The human check is not configured yet.");
  if (!token || typeof token !== "string") return false;
  const form = new FormData();
  form.append("secret", env.TURNSTILE_SECRET);
  form.append("response", token);
  if (ip !== "unknown") form.append("remoteip", ip);
  const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form });
  const out = await res.json().catch(() => ({}));
  if (!out.success) console.log("Turnstile failed: " + JSON.stringify(out["error-codes"] || out));
  return out.success === true;
}

function dim(value, label) {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 1 || n > 240) throw fail(400, `${label} must be between 1 and 240 inches.`);
  return Math.round(n * 1000) / 1000;
}

async function getToken(env) {
  if (cachedToken && cachedToken.expiresAt > Date.now() + 60_000) return cachedToken.value;
  const res = await fetch(`${APS}/authentication/v2/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: "Basic " + btoa(`${env.APS_CLIENT_ID}:${env.APS_CLIENT_SECRET}`),
    },
    body: new URLSearchParams({ grant_type: "client_credentials", scope: "code:all data:read data:write" }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(`APS token failed (${res.status}): ${JSON.stringify(data)}`);
  cachedToken = { value: data.access_token, expiresAt: Date.now() + data.expires_in * 1000 };
  return cachedToken.value;
}

async function apsJson(token, method, url, body) {
  const res = await fetch(url, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(`APS ${method} ${url} failed (${res.status}): ${JSON.stringify(data)}`);
  return data;
}

function fail(httpStatus, publicMessage) {
  return Object.assign(new Error(publicMessage), { httpStatus, publicMessage });
}
