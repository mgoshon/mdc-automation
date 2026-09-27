# Builds the add-in and packages it as the AppBundle zip Autodesk expects:
#   MDCBoxFamily.zip
#     MDCBoxFamily.bundle/
#       PackageContents.xml
#       Contents/MDCBoxFamily.addin + DLLs
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

dotnet build "$root\MDCBoxFamily.csproj" -c Release

$out   = Join-Path $root "bin\Release\net8.0-windows"
$dist  = Join-Path $root "dist"
$stage = Join-Path $dist "MDCBoxFamily.bundle"

if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
New-Item (Join-Path $stage "Contents") -ItemType Directory -Force | Out-Null

Copy-Item (Join-Path $root "PackageContents.xml") $stage
Copy-Item (Join-Path $root "MDCBoxFamily.addin") (Join-Path $stage "Contents")
Copy-Item (Join-Path $out "*.dll") (Join-Path $stage "Contents")

# RevitAPI must not ship in the bundle; the cloud engine provides it.
Remove-Item (Join-Path $stage "Contents\RevitAPI*.dll") -ErrorAction SilentlyContinue

Compress-Archive -Path $stage -DestinationPath (Join-Path $dist "MDCBoxFamily.zip") -Force
Write-Host "Bundle ready: $dist\MDCBoxFamily.zip"
