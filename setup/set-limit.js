// Sets (or shows) a monthly cap on Automation API processing time for your app.
// Once the cap is reached, Autodesk rejects new work items until the next calendar month.
//
// Usage:
//   node set-limit.js          show the current limit
//   node set-limit.js 2        cap at 2 processing hours per month
//   node set-limit.js 0.5      cap at 30 minutes per month
import { DA, loadEnv, getToken, api, must } from "./aps.js";

const env = loadEnv();
const token = await getToken(env, "code:all");
const hours = process.argv[2];

// The owner can be referenced as "me"; fall back to the nickname if the service wants it.
async function call(method, body) {
  let r = await api(token, method, `${DA}/servicelimits/me`, body);
  if (r.status === 400 || r.status === 404) r = await api(token, method, `${DA}/servicelimits/${env.APS_NICKNAME}`, body);
  return r;
}

if (hours !== undefined) {
  const value = Number(hours);
  if (!Number.isFinite(value) || value <= 0) throw new Error("Pass a positive number of hours, for example: node set-limit.js 2");
  must(await call("PUT", { frontendLimits: { limitMonthlyProcessingTimeInHours: value } }), "Set service limit");
  console.log(`Monthly cap set to ${value} processing hour(s).`);
}

const current = await call("GET");
if (current.ok) {
  const h = current.data?.frontendLimits?.limitMonthlyProcessingTimeInHours;
  console.log(h ? `Current monthly cap: ${h} hour(s)` : "No monthly cap is set.");
  console.log(JSON.stringify(current.data, null, 2));
} else if (current.status === 404) {
  console.log("No monthly cap is set.");
} else {
  must(current, "Read service limits");
}
