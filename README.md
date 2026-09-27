# MDC Automation: Box Family Generator (proof of concept)

Generates a Revit 2025 Generic Model family (.rfa) in the cloud from width, depth, and height,
using the Autodesk Platform Services (APS) Automation API. No Revit desktop is involved at run time.

```
Website (generator.html)
   |  POST /api/generate
   v
Cloudflare Worker (worker/)  -- holds APS keys, validates input, submits the job
   |  work item
   v
APS Automation API  -- runs your add-in (addin/) inside cloud Revit
   |  result.rfa saved to your OSS bucket
   v
Worker returns a 30-minute download link to the page
```

## Folder map

| Folder | What it is |
|---|---|
| `addin/` | C# Revit 2025 add-in (no UI), bundle packaging script, and local test setup |
| `setup/` | Node scripts: deploy everything to APS, run a test job |
| `worker/` | Cloudflare Worker API your website calls |
| `site/` | `generator.html` test page with live preview |

## What you need

- Windows PC with the .NET 8 SDK (`dotnet --version` should show 8.x)
- Node.js 20 or newer
- Revit 2025 installed (only for the family template file and for opening results)
- A free Autodesk developer account at aps.autodesk.com
- Your Cloudflare account

## Step 1: Create the APS app

1. Sign in at aps.autodesk.com and open the developer hub (create a hub if prompted).
2. Create an application (server-to-server / traditional web app is fine).
3. Enable the **Automation API** and **Data Management API** for it.
4. Copy the **Client ID** and **Client Secret**.

## Step 2: Build the add-in bundle

```powershell
cd addin
.\build-bundle.ps1
```

Output: `addin\dist\MDCBoxFamily.zip`. If NuGet restore fails on a package version, open the
package on nuget.org and pin the latest 2025.x version in `MDCBoxFamily.csproj`.

## Step 2b: Test locally in desktop Revit (recommended before every deploy)

Local runs are free and let you step through the code in Visual Studio. Autodesk's
AutomationServiceHandler add-in fires the same "ready" event inside desktop Revit that the cloud
engine fires, so your add-in runs exactly as it would in the cloud.

**One-time setup**

1. Get the handler: clone
   `github.com/autodesk-platform-services/aps-automation-csharp-revit.local.debug.tool`,
   build the `AutomationServiceHandler2025` project, and copy its `.addin` file into
   `C:\ProgramData\Autodesk\Revit\Addins\2025\` as described in that repo's README.
2. Close Revit, then run:
   ```powershell
   cd addin
   .\install-local.ps1
   ```
   This builds a Debug copy, registers it with Revit 2025, and creates `C:\MDC\LocalTest`
   with `template.rft` and `params.json`.
3. Open Revit 2025, start a new blank project, and save it as `C:\MDC\LocalTest\host.rvt`.
   The handler needs an open model to start; the add-in ignores its contents.

**Each test run**

1. Edit `C:\MDC\LocalTest\params.json` with the size you want to try.
2. Open `host.rvt` in Revit 2025 and run the AutomationServiceHandler command from the ribbon.
3. Check `C:\MDC\LocalTest\result.rfa`. Messages starting with `MDC:` appear in the
   Visual Studio Output window when debugging.

**Debugging in Visual Studio:** open `MDCBoxFamily.csproj`, pick the "Revit 2025" launch
profile, set breakpoints in `BoxBuilder.cs`, and press F5. Revit starts with the debugger attached.

**After code changes:** close Revit, re-run `.\install-local.ps1`, and test again. When it works
locally, run `.\build-bundle.ps1` and `node deploy.js` to push it to the cloud.

**Remove the local registration:** `.\install-local.ps1 -Uninstall`

## Step 3: Deploy to APS

```powershell
cd setup
copy .env.example .env     # then fill in the values
node deploy.js
```

Check `TEMPLATE_PATH` in `.env`. The default is the imperial Generic Model template from a
standard Revit 2025 install. Re-run `node deploy.js` any time you change the add-in; it publishes
a new version and moves the `prod` alias to it.

## Step 4: Run a test job

```powershell
node test-workitem.js 24 30 42 "Test Box"
```

It prints the job status, a report link, and saves `out\Test_Box.rfa`. Open it in Revit 2025.
If a job fails, open the report link and search for `MDC ERROR`.

## Step 5: Deploy the Worker

```powershell
cd worker
# edit wrangler.toml: APS_NICKNAME and APS_BUCKET must match your .env
npx wrangler login
npx wrangler secret put APS_CLIENT_ID
npx wrangler secret put APS_CLIENT_SECRET
npx wrangler secret put ACCESS_KEY      # make up a long random string
npx wrangler deploy
```

Note the `workers.dev` URL it prints.

## Step 6: Hook up the test page

1. In `site/generator.html`, set `API_BASE` to your Worker URL.
2. Put the page on your site at an unlinked path (for example `/tools/generator.html`).
   It has `noindex` so search engines skip it.
3. Open it, enter the access key, and generate a family.

## Costs and safety

- Every job uses APS Automation time. The Free tier includes limited monthly usage; watch the
  usage page in the APS developer hub while testing.
- The access key keeps random visitors from running jobs. Before a public launch, add
  Cloudflare Turnstile and per-visitor rate limits, or tie generation to a paid order.
- APS keys live only in Worker secrets and `.env`. Keep `.env` out of any repo.

## Troubleshooting

| Problem | Likely cause |
|---|---|
| Local run: `params.json not found` | `host.rvt` is not in `C:\MDC\LocalTest`, or Revit was open when `install-local.ps1` set `MDC_WORKDIR` (restart Revit) |
| Local run: add-in not loading | Revit was open during install, or the handler `.addin` is missing from the 2025 Addins folder |
| `deploy.js` 401/403 | Automation API or Data Management API not enabled on the APS app |
| Nickname 409 | Normal after the first deploy |
| Job `failedInstructions` | Activity or AppBundle mismatch; re-run `deploy.js` and check `REVIT_ENGINE` |
| Job `failedDownload` | Template missing in the bucket, or bucket name mismatch between `.env` and `wrangler.toml` |
| Job `failedExecution` | Add-in error; see `MDC ERROR` in the report |
| Browser CORS error | `ALLOWED_ORIGIN` in `wrangler.toml` does not match the page's origin |

## Roadmap

- **Phase 2:** make the family flex (reference planes, labeled dimensions tied to Width/Depth/Height).
- **Phase 3:** material and identity data, then more product types (supports, sleeves, equipment pads).
- **Phase 4:** 2D drafting-view details and DWG output using the AutoCAD engine.
- **Phase 5:** tie generation to Stripe checkout so paid orders trigger the job.
