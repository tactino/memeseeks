# Build the Windows installer: memeseeks-windows-setup.exe.
#
#   powershell -File installer\windows\build.ps1 [-Wheel dist\memeseeks-X-py3-none-any.whl] [-Stage]
#
# Puts a Python 3.12 of its own (python-build-standalone, which can be moved) with memeseeks and everything it
# needs into installer\windows\build\app, then has Inno Setup make one setup.exe of it. Nothing is downloaded on
# the user's computer but the models, on the first start, as before. -Stage stops before Inno Setup.
# Needs uv; Inno Setup 6 (iscc) unless -Stage. The release workflow runs this on a Windows runner.

param([string]$Wheel = "", [switch]$Stage)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$build = Join-Path $PSScriptRoot "build"
$app = Join-Path $build "app"
if (Test-Path $app) { Remove-Item $app -Recurse -Force }
New-Item -ItemType Directory -Force -Path $app | Out-Null

if (-not $Wheel) {
  & uv build --wheel --out-dir (Join-Path $build "dist") $repo
  if ($LASTEXITCODE -ne 0) { throw "building the wheel failed" }
  $Wheel = (Get-ChildItem (Join-Path $build "dist") -Filter "memeseeks-*.whl" | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
}
$Wheel = (Resolve-Path $Wheel).Path
$version = ([IO.Path]::GetFileName($Wheel) -split "-")[1]
Write-Host "memeseeks $version from $Wheel"

# ---- Python 3.12 of its own ----
$pythons = Join-Path $build "pythons"
& uv python install 3.12 --install-dir $pythons
if ($LASTEXITCODE -ne 0) { throw "getting Python 3.12 failed" }
$found = Get-ChildItem $pythons -Directory | Where-Object { $_.Name -like "cpython-3.12*-windows-x86_64-*" } | Select-Object -First 1
if (-not $found) { throw "no Python 3.12 under $pythons" }
Copy-Item $found.FullName (Join-Path $app "python") -Recurse
$python = Join-Path $app "python\python.exe"
Remove-Item (Join-Path $app "python\Lib\EXTERNALLY-MANAGED") -ErrorAction SilentlyContinue  # this copy is ours

# ---- memeseeks and what it needs; on Windows the torch that PyPI has is the CPU build ----
& uv pip install --python $python --link-mode copy "memeseeks[ml,serve] @ file:///$($Wheel -replace '\\', '/')"
if ($LASTEXITCODE -ne 0) { throw "installing memeseeks failed" }
Get-ChildItem (Join-Path $app "python") -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Copy-Item (Join-Path $repo "src\memeseeks\web\icons\memeseeks.ico") (Join-Path $app "memeseeks.ico")
& $python -c "import memeseeks.tray, memeseeks.wintray, torch, transformers, uvicorn; print('imports ok')"
if ($LASTEXITCODE -ne 0) { throw "the staged app does not import" }
$size = (Get-ChildItem $app -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("staged {0:N0} MB in {1}" -f $size, $app)
if ($Stage) { return }

# ---- Inno Setup ----
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 (ISCC.exe) not found" }
$lang = Join-Path (Split-Path $iscc) "Languages\ChineseSimplified.isl"
if (-not (Test-Path $lang)) {  # the Chinese translation ships with Inno Setup's source, among the unofficial ones
  $lang = Join-Path $build "ChineseSimplified.isl"
  Invoke-WebRequest "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/Unofficial/ChineseSimplified.isl" -OutFile $lang -UseBasicParsing
}
& $iscc "/DAppVersion=$version" "/DBuildDir=$build" "/DLangFile=$lang" (Join-Path $PSScriptRoot "memeseeks.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Get-Item (Join-Path $build "memeseeks-windows-setup.exe") | ForEach-Object { Write-Host ("{0} {1:N0} MB" -f $_.FullName, ($_.Length / 1MB)) }
