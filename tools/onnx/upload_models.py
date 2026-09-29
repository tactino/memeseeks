"""Upload the 8-bit models and their card to the Hugging Face repository the app downloads from.

  HF_TOKEN=... python tools/onnx/upload_models.py OUT_DIR

Prints the commit, which models/store.py can pin as REVISION.
"""

import os
import sys
from pathlib import Path

from huggingface_hub import HfApi

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from memeseeks.models.store import FOLDERS, REPO  # noqa: E402

out = Path(sys.argv[1])
api = HfApi(token=os.environ["HF_TOKEN"])
api.create_repo(REPO, repo_type="model", exist_ok=True)
source = f"https://github.com/tactino/memeseeks/commit/{os.environ.get('GITHUB_SHA', 'local')}"
api.upload_folder(repo_id=REPO, folder_path=str(out), allow_patterns=[f"{f}/*" for f in FOLDERS.values()],
                  commit_message=f"8-bit models built by {source}")
info = api.upload_file(repo_id=REPO, path_or_fileobj=str(Path(__file__).with_name("MODEL_CARD.md")),
                       path_in_repo="README.md", commit_message="model card")
print("uploaded to", REPO, "at", info.oid)
