# 迷因捕手 · memeseeks — install on Windows (PowerShell 5.1 or newer).
#
#   irm https://raw.githubusercontent.com/tactino/memeseeks/main/scripts/install.ps1 | iex
#
# With options, say nothing on drive C:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/tactino/memeseeks/main/scripts/install.ps1))) -Dir D:\memeseeks -Library D:\memeseeks-library
#
#   -Dir      the program, its Python and (unless -Models) the models   default %LOCALAPPDATA%\memeseeks
#   -Library  your memes' index, 图集 and collected images              default %USERPROFILE%\.memeseeks
#   -Models   the Hugging Face cache, e.g. one you already have         default <Dir>\models
#
# (This file is UTF-8 without a BOM, as irm | iex needs; Windows PowerShell would misread it with -File.)
#
# Everything goes into one folder (default %LOCALAPPDATA%\memeseeks): its own uv, its own Python, the app,
# and the models (about 3.9 GB, fetched on the first start). Nothing is added to PATH or the registry;
# uninstalling is deleting that folder and the two shortcuts. Your library stays in %USERPROFILE%\.memeseeks.
# Run it again to update. From China it uses mirrors for PyPI, Python and the models (-Mirror auto|on|off).

param(
  [string]$Dir = (Join-Path $env:LOCALAPPDATA "memeseeks"),
  [string]$Library = "",
  [string]$Models = "",
  [ValidateSet("auto", "on", "off")] [string]$Mirror = "auto",
  [string]$Source = "https://github.com/tactino/memeseeks/archive/refs/heads/main.zip",
  [string[]]$ShortcutDirs = @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs")),
  [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest is many times slower with its progress bar
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

function Say($text) { Write-Host "  $text" }
function Step($text) { Write-Host ""; Write-Host "» $text" -ForegroundColor Yellow }

Write-Host ""
Write-Host "迷因捕手 · memeseeks 安装" -ForegroundColor Yellow
$Dir = [IO.Path]::GetFullPath($Dir)
if ($Library) { $Library = [IO.Path]::GetFullPath($Library) }
if ($Models) { $Models = [IO.Path]::GetFullPath($Models) }
$LibraryShown = if ($Library) { $Library } else { Join-Path $env:USERPROFILE ".memeseeks" }
Say "程序：$Dir"
Say "图库：$LibraryShown"
Say "模型：$(if ($Models) { $Models } else { Join-Path $Dir 'models' })"
New-Item -ItemType Directory -Force -Path $Dir | Out-Null

# ---- mirrors: used when Hugging Face cannot be reached quickly (usually: from China) ----
if ($Mirror -eq "auto") {
  $Mirror = "off"
  try { Invoke-WebRequest "https://huggingface.co/api/models/BAAI/bge-m3" -Method Head -TimeoutSec 6 -UseBasicParsing | Out-Null }
  catch { $Mirror = "on" }
}
$PyPI = "https://pypi.org"
if ($Mirror -eq "on") {
  Say "使用国内镜像（PyPI：清华；Python：npmmirror；模型：hf-mirror）"
  $PyPI = "https://pypi.tuna.tsinghua.edu.cn"
  $env:UV_DEFAULT_INDEX = "$PyPI/simple"
  $env:UV_PYTHON_INSTALL_MIRROR = "https://registry.npmmirror.com/-/binary/python-build-standalone"
}
$env:UV_CACHE_DIR = Join-Path $Dir "cache"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Dir "python"

# ---- uv, from PyPI (a wheel is a zip holding uv.exe): no GitHub needed, nothing installed system-wide ----
$Uv = Join-Path $Dir "bin\uv.exe"
if (-not (Test-Path $Uv)) {
  Step "下载 uv（Python 包管理工具）"
  $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "win_arm64" } else { "win_amd64" }
  $page = Invoke-WebRequest "$PyPI/simple/uv/" -UseBasicParsing
  $wheels = [regex]::Matches($page.Content, "href=""([^""]*/uv-(\d+)\.(\d+)\.(\d+)-py3-none-$arch\.whl)#sha256=([0-9a-f]+)""")
  if ($wheels.Count -eq 0) { throw "在 $PyPI 上没找到 uv 的 $arch 安装包" }
  $best = $wheels | Sort-Object { [int]$_.Groups[2].Value }, { [int]$_.Groups[3].Value }, { [int]$_.Groups[4].Value } | Select-Object -Last 1
  $url = [Uri]::new([Uri]"$PyPI/simple/uv/", $best.Groups[1].Value).AbsoluteUri
  $zip = Join-Path $Dir "uv.zip"
  Invoke-WebRequest $url -OutFile $zip -UseBasicParsing
  # .NET directly, not Get-FileHash / Expand-Archive: those are script modules that a mixed-up PSModulePath
  # (PowerShell 7 installed next to Windows PowerShell) can hide
  $stream = [IO.File]::OpenRead($zip)
  try { $hash = -join ([Security.Cryptography.SHA256]::Create().ComputeHash($stream) | ForEach-Object { $_.ToString("x2") }) }
  finally { $stream.Close() }
  if ($hash -ne $best.Groups[5].Value) { throw "uv 下载不完整（校验失败），请重试" }
  $unpacked = Join-Path $Dir "uv-unpacked"
  if (Test-Path $unpacked) { Remove-Item $unpacked -Recurse -Force }
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  [IO.Compression.ZipFile]::ExtractToDirectory($zip, $unpacked)
  New-Item -ItemType Directory -Force -Path (Split-Path $Uv) | Out-Null
  Copy-Item (Get-ChildItem $unpacked -Recurse -Filter "uv.exe" | Select-Object -First 1).FullName $Uv
  Remove-Item $zip, $unpacked -Recurse -Force
  Say "uv $((& $Uv --version) -replace '^uv ', '')"
}

# ---- Python 3.12 of its own (not Anaconda's: its old MSVC runtime breaks torch >= 2.9) ----
$Venv = Join-Path $Dir ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Python)) {
  Step "准备 Python 3.12"
  & $Uv venv --managed-python --python 3.12 $Venv --quiet
  if ($LASTEXITCODE -ne 0) { throw "创建 Python 环境失败" }
}

# ---- the app; on Windows the torch that PyPI has is the CPU build ----
Step "安装迷因捕手（第一次大约 700 MB，需要几分钟）"
& $Uv pip install --python $Python "memeseeks[ml,serve] @ $Source" --reinstall-package memeseeks --refresh-package memeseeks
if ($LASTEXITCODE -ne 0) { throw "安装失败。网络不稳时重新运行一次即可，已下载的部分不会重下" }
& $Uv cache prune --quiet 2>$null

# ---- the launcher and shortcuts ----
Step "创建快捷方式"
$ico = Join-Path $Dir "memeseeks.ico"
Copy-Item (Join-Path $Venv "Lib\site-packages\memeseeks\web\icons\memeseeks.ico") $ico -Force
$launcher = Join-Path $Dir "memeseeks.cmd"
$lines = @(
  "@echo off",
  "rem 迷因捕手: double-click to start; close this window to stop.",
  "chcp 65001 >nul",
  "title memeseeks - close this window to stop",
  "set PYTHONIOENCODING=utf-8"
)
$lines += if ($Models) { "set ""HF_HOME=$Models""" } else { "set ""HF_HOME=%~dp0models""" }
if ($Library) { $lines += "set ""MEMESEEKS_HOME=$Library""" }
if ($Mirror -eq "on") { $lines += "set ""HF_ENDPOINT=https://hf-mirror.com""" }
$lines += @("""%~dp0.venv\Scripts\memeseeks.exe"" serve --open %*", "if errorlevel 1 pause")
# its own paths are relative to it (%~dp0); -Library / -Models are written out after chcp 65001, so any name works
[IO.File]::WriteAllLines($launcher, $lines, (New-Object Text.UTF8Encoding $false))
$shell = New-Object -ComObject WScript.Shell
foreach ($where in $ShortcutDirs) {
  if (-not $where) { continue }
  New-Item -ItemType Directory -Force -Path $where | Out-Null
  $path = Join-Path $where "迷因捕手.lnk"
  $link = $shell.CreateShortcut($path)
  if ((Test-Path $path) -and $link.TargetPath -ne $launcher) {  # someone else's: leave it alone
    Say "已有同名快捷方式，没有覆盖：$path（这次装的启动文件是 $launcher）"
    continue
  }
  $link.TargetPath = $launcher
  $link.WorkingDirectory = $Dir
  $link.IconLocation = $ico
  $link.Description = "迷因捕手 · memeseeks"
  $link.Save()
  Say "快捷方式：$where\迷因捕手.lnk"
}

Write-Host ""
Write-Host "装好了。" -ForegroundColor Green
Say "以后双击桌面上的「迷因捕手」启动，关掉它的黑色窗口就会停止。"
Say "第一次启动会下载约 3.9 GB 的模型，网页上能看到进度；下完就能搜索。"
Say "卸载：删除 $Dir 和两个快捷方式。你的图库在 $LibraryShown，不会被删除。"
if (-not $NoLaunch) { Start-Process -FilePath $launcher -WorkingDirectory $Dir }
