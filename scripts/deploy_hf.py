"""Deploy AP Autopilot to a Hugging Face Docker Space (free, no card).

Prerequisite (once): log in so a token is stored locally, e.g.  hf auth login
Then:  python scripts/deploy_hf.py [space-name]

Uploads exactly the files tracked by git (so .env, the database and videos never leave this machine)
and prepends the Space settings block Hugging Face requires to README.md. Set GEMINI_API_KEY as a
secret in the Space settings afterwards.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
SPACE_HEADER = """---
title: AP Autopilot
emoji: 🧾
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
pinned: false
short_description: Invoice PDF to an explainable approve/review/reject decision
---

"""


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "ap-autopilot"
    api = HfApi()
    user = api.whoami()["name"]
    repo_id = f"{user}/{name}"
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)

    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            dst = Path(tmp) / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, dst)
        readme = Path(tmp) / "README.md"
        readme.write_text(SPACE_HEADER + readme.read_text())
        api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=tmp,
                          commit_message="Deploy AP Autopilot", delete_patterns=["*"])
    print(f"Space:   https://huggingface.co/spaces/{repo_id}")
    print(f"App URL: https://{user.lower()}-{name.lower()}.hf.space")
    print(f"Secrets: https://huggingface.co/spaces/{repo_id}/settings  (add GEMINI_API_KEY)")


if __name__ == "__main__":
    main()
