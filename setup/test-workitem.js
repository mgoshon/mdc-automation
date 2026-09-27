// Runs one job end to end and downloads the result.
// Usage: node test-workitem.js [widthIn] [depthIn] [heightIn] [typeName]
import fs from "node:fs";
import { DA, ACTIVITY_ID, ALIAS, TEMPLATE_KEY, loadEnv, getToken, api, must, ossDownloadUrl, sleep } from "./aps.js";

const env = loadEnv();
const token = await getToken(env);
const [w = 24, d = 30, h = 42, typeName = "Test Box"] = process.argv.slice(2);

const params = { widthIn: Number(w), depthIn: Number(d), heightIn: Number(h), typeName };
const resultKey = `results/test-${Date.now()}.rfa`;
const oss = (key) => `urn:adsk.objects:os.object:${env.APS_BUCKET}/${key}`;
const auth = { Authorization: `Bearer ${token}` };

const workItem = must(await api(token, "POST", `${DA}/workitems`, {
  activityId: `${env.APS_NICKNAME}.${ACTIVITY_ID}+${ALIAS}`,
  arguments: {
    template: { url: oss(TEMPLATE_KEY), headers: auth },
    params:   { url: "data:application/json," + JSON.stringify(params) },
    result:   { verb: "put", url: oss(resultKey), headers: auth },
  },
}), "Submit work item");

console.log(`Work item ${workItem.id} submitted with`, params);

let status;
do {
  await sleep(5000);
  status = must(await api(token, "GET", `${DA}/workitems/${workItem.id}`), "Check work item");
  console.log(`  ${status.status}`);
} while (["pending", "inprogress"].includes(status.status));

console.log(`Report: ${status.reportUrl}`);
if (status.status !== "success") {
  console.log("Job did not succeed. Open the report link above for the Revit log (look for 'MDC ERROR').");
  process.exit(1);
}

const url = await ossDownloadUrl(token, env.APS_BUCKET, resultKey);
fs.mkdirSync("out", { recursive: true });
const file = `out/${typeName.replace(/[^A-Za-z0-9_-]/g, "_")}.rfa`;
fs.writeFileSync(file, Buffer.from(await (await fetch(url)).arrayBuffer()));
console.log(`Saved ${file}. Open it in Revit 2025 to check the result.`);
