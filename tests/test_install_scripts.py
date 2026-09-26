import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PS1, SH = ROOT / "scripts" / "install.ps1", ROOT / "scripts" / "install.sh"


def test_the_windows_installer_is_utf8_without_a_bom():
    data = PS1.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")  # `irm | iex` would choke on it
    data.decode("utf-8")


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell is not installed")
def test_the_windows_installer_parses():
    check = ("$e = $null; [void][System.Management.Automation.Language.Parser]::ParseInput("
             f"[IO.File]::ReadAllText('{PS1}', [Text.Encoding]::UTF8), [ref]$null, [ref]$e); "
             "if ($e) { $e | ForEach-Object { $_.ToString() }; exit 1 }")
    subprocess.run(["pwsh", "-NoProfile", "-Command", check], check=True, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("sh") is None, reason="no POSIX shell")
def test_the_unix_installer_parses():
    subprocess.run(["sh", "-n", str(SH)], check=True, capture_output=True)


def test_the_installers_find_their_icons_in_the_package():
    icons = ROOT / "src" / "memeseeks" / "web" / "icons"
    assert "web\icons\memeseeks.ico" in PS1.read_text(encoding="utf-8") and (icons / "memeseeks.ico").is_file()
    assert "web/icons/icon-512.png" in SH.read_text(encoding="utf-8") and (icons / "icon-512.png").is_file()


def test_the_readme_points_at_the_installers():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for script in ("scripts/install.ps1", "scripts/install.sh"):
        assert f"https://raw.githubusercontent.com/tactino/memeseeks/main/{script}" in readme
