import re
from pathlib import Path

import memeseeks


def test_version_is_the_packages():
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert memeseeks.__version__ == re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
