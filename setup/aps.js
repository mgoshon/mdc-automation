// Shared helpers for talking to Autodesk Platform Services (APS).
import fs from "node:fs";

export const APS = "https://developer.api.autodesk.com";
export const DA = `${APS}/da/us-east/v3`;

export const BUNDLE_ID = "MDCBoxFamily";
export const ACTIVITY_ID = "MDCBoxFamily";
export const ALIAS = "prod";
export const TEMPLATE_KEY = "templates/generic-model.rft";

export function loadEnv(file = ".env") {
  if (!fs.existsSync(file)) throw new Error(`Missing ${file}. Copy .env.example to .env and fill it in.`);
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m && !line.trim().startsWith("#")) process.env[m[1]] ??= m[2];
  }
  for (const k of ["APS_CLIENT_ID", "APS_CLIENT_SECRET", "APS_NICKNAME", "APS_BUCKET", "REVIT_ENGINE"]) {
    if (!process.env[k]) throw new Error(`${k} is not set in .env`);
  }
  return process.env;
}

export async function getToken(env, scopes = "code:all bucket:create bucket:read data:read data:write") {
  const res = await fetch(`${APS}/authentication/v2/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: "Basic " + Buffer.from(`${env.APS_CLIENT_ID}:${env.APS_CLIENT_SECRET}`).toString("base64"),
    },
    body: new URLSearchParams({ grant_type: "client_credentials", scope: scopes }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(`Token request failed (${res.status}): ${JSON.stringify(data)}`);
  return data.access_token;
}

// JSON request helper. Returns { status, ok, data } and never throws on HTTP errors.
export async function api(token, method, url, body) {
  const res = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  return { status: res.status, ok: res.ok, data };
}

export function must(result, label) {
  if (!result.ok) throw new Error(`${label} failed (${result.status}): ${JSON.stringify(result.data)}`);
  return result.data;
}

// Upload a local file to an OSS bucket using the signed S3 upload flow.
export async function ossUpload(token, bucket, objectKey, filePath) {
  const base = `${APS}/oss/v2/buckets/${bucket}/objects/${encodeURIComponent(objectKey)}/signeds3upload`;
  const start = must(await api(token, "GET", base), "Get signed upload URL");
  const put = await fetch(start.urls[0], { method: "PUT", body: fs.readFileSync(filePath) });
  if (!put.ok) throw new Error(`S3 upload failed (${put.status}): ${await put.text()}`);
  must(await api(token, "POST", base, { uploadKey: start.uploadKey }), "Complete upload");
}

export async function ossDownloadUrl(token, bucket, objectKey, minutes = 30) {
  const url = `${APS}/oss/v2/buckets/${bucket}/objects/${encodeURIComponent(objectKey)}/signeds3download?minutesExpiration=${minutes}`;
  return must(await api(token, "GET", url), "Get signed download URL").url;
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
