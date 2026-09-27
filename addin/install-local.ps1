# Sets up local testing in desktop Revit 2025 with Autodesk's AutomationServiceHandler.
#   .\install-local.ps1              build Debug, register the add-in, create the test folder
#   .\install-local.ps1 -Uninstall   remove the local add-in registration
# Close Revit before running this (Revit locks the DLL while open).
param(
  [switch]$Uninstall,
  [string]$TestDir = "C:\MDC\LocalTest",
  [string]$TemplatePath = "C:\ProgramData\Autodesk\RVT 2025\Family Templates\English_I\Generic Model.rft"
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$addinsDir = Join-Path $env:ProgramData "Autodesk\Revit\Addins\2025"
$addinFile = Join-Path $addinsDir "MDCBoxFamily.local.addin"

if ($Uninstall) {
  Remove-Item $addinFile -ErrorAction SilentlyContinue
  Write-Host "Removed $addinFile"
  exit 0
}

if (Get-Process Revit -ErrorAction SilentlyContinue) { throw "Close Revit first, then run this again." }

dotnet build "$root\MDCBoxFamily.csproj" -c Debug
$dll = Join-Path $root "bin\Debug\net8.0-windows\MDCBoxFamily.dll"
if (-not (Test-Path $dll)) { throw "Build output not found: $dll" }

# Register the add-in with an absolute path to the Debug build.
New-Item $addinsDir -ItemType Directory -Force | Out-Null
$addin = (Get-Content "$root\MDCBoxFamily.addin" -Raw) -replace '<Assembly>.*</Assembly>', "<Assembly>$dll</Assembly>"
Set-Content -Path $addinFile -Value $addin -Encoding UTF8
Write-Host "Registered: $addinFile"

# Test folder with the same file names the cloud job uses.
New-Item $TestDir -ItemType Directory -Force | Out-Null
if (-not (Test-Path $TemplatePath)) { throw "Template not found: $TemplatePath (pass -TemplatePath)" }
Copy-Item $TemplatePath (Join-Path $TestDir "template.rft") -Force
if (-not (Test-Path (Join-Path $TestDir "params.json"))) {
  '{ "widthIn": 24, "depthIn": 30, "heightIn": 42, "typeName": "Local Test" }' |
    Set-Content (Join-Path $TestDir "params.json") -Encoding UTF8
}
[Environment]::SetEnvironmentVariable("MDC_WORKDIR", $TestDir, "User")

Write-Host ""
Write-Host "Test folder ready: $TestDir"
Write-Host "  template.rft  (copied)"
Write-Host "  params.json   (edit to try other sizes)"
Write-Host "Still needed once: save any blank Revit 2025 project as $TestDir\host.rvt"
