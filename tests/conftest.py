import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("MEMESEEKS_ML_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="needs model weights; set MEMESEEKS_ML_TESTS=1 on the GPU box")
    for item in items:
        if "ml" in item.keywords:
            item.add_marker(skip)
