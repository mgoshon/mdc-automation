// One command to set up (or update) everything on the APS side:
//   1. Nickname for your APS app
//   2. OSS bucket + Generic Model template upload
//   3. AppBundle (your add-in zip), new version + "prod" alias
//   4. Activity (how Revit runs your add-in), new version + "prod" alias
// Safe to re-run after every add-in change.
import fs from "node:fs";
import path from "node:path";
import {
  DA, APS, BUNDLE_ID, ACTIVITY_ID, ALIAS, TEMPLATE_KEY,
  loadEnv, getToken, api, must, ossUpload,
} from "./aps.js";

const env = loadEnv();
const token = await getToken(env);
const nick = env.APS_NICKNAME;
const engine = env.REVIT_ENGINE;

// 1. Nickname. Only settable before the app owns any DA resources, so a 409 later is expected.
{
  const r = await api(token, "PATCH", `${DA}/forgeapps/me`, { nickname: nick });
  if (r.ok) console.log(`Nickname set: ${nick}`);
  else if (r.status === 409) console.log(`Nickname already in place (409), continuing.`);
  else must(r, "Set nickname");
}

// 2. Bucket and template.
{
  const r = await api(token, "POST", `${APS}/oss/v2/buckets`, { bucketKey: env.APS_BUCKET, policyKey: "persistent" });
  if (r.ok) console.log(`Bucket created: ${env.APS_BUCKET}`);
  else if (r.status === 409) console.log(`Bucket exists: ${env.APS_BUCKET}`);
  else must(r, "Create bucket");

  if (!env.TEMPLATE_PATH || !fs.existsSync(env.TEMPLATE_PATH))
    throw new Error(`TEMPLATE_PATH not found: ${env.TEMPLATE_PATH}`);
  await ossUpload(token, env.APS_BUCKET, TEMPLATE_KEY, env.TEMPLATE_PATH);
  console.log(`Template uploaded: ${TEMPLATE_KEY}`);
}

// Helper: create the resource, or add a new version if it already exists, then point the alias at it.
async function publish(kind, id, createBody, versionBody) {
  let r = await api(token, "POST", `${DA}/${kind}`, createBody);
  if (r.status === 409) r = await api(token, "POST", `${DA}/${kind}/${id}/versions`, versionBody);
  const data = must(r, `Publish ${kind}/${id}`);

  let a = await api(token, "POST", `${DA}/${kind}/${id}/aliases`, { id: ALIAS, version: data.version });
  if (a.status === 409) a = await api(token, "PATCH", `${DA}/${kind}/${id}/aliases/${ALIAS}`, { version: data.version });
  must(a, `Alias ${kind}/${id}+${ALIAS}`);

  console.log(`${kind}/${id} version ${data.version} -> alias "${ALIAS}"`);
  return data;
}

// 3. AppBundle.
{
  const zipPath = path.resolve(env.BUNDLE_ZIP || "../addin/dist/MDCBoxFamily.zip");
  if (!fs.existsSync(zipPath)) throw new Error(`Bundle zip not found: ${zipPath}. Run addin\\build-bundle.ps1 first.`);

  const body = { engine, description: "MDC Box Family generator" };
  const data = await publish("appbundles", BUNDLE_ID, { id: BUNDLE_ID, ...body }, body);

  // Upload the zip to the pre-signed location Autodesk returned.
  const form = new FormData();
  for (const [k, v] of Object.entries(data.uploadParameters.formData)) form.append(k, v);
  form.append("file", new Blob([fs.readFileSync(zipPath)]), path.basename(zipPath));
  const up = await fetch(data.uploadParameters.endpointURL, { method: "POST", body: form });
  if (!up.ok) throw new Error(`AppBundle upload failed (${up.status}): ${await up.text()}`);
  console.log(`AppBundle zip uploaded`);
}

// 4. Activity.
{
  const body = {
    commandLine: [`$(engine.path)\\\\revitcoreconsole.exe /al "$(appbundles[${BUNDLE_ID}].path)"`],
    parameters: {
      template: { verb: "get", localName: "template.rft", required: true, description: "Generic Model family template" },
      params:   { verb: "get", localName: "params.json",  required: true, description: "Box dimensions in inches" },
      result:   { verb: "put", localName: "result.rfa",   required: true, description: "Generated family" },
    },
    engine,
    appbundles: [`${nick}.${BUNDLE_ID}+${ALIAS}`],
    description: "Creates a Generic Model box family from width, depth, and height",
  };
  await publish("activities", ACTIVITY_ID, { id: ACTIVITY_ID, ...body }, body);
}

console.log(`\nDone. Activity id for work items: ${nick}.${ACTIVITY_ID}+${ALIAS}`);
