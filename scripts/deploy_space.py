"""Create or update the Hugging Face Space and its secrets.  Usage: python scripts/deploy_space.py [space_name]"""
import sys
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
ENV = dotenv_values(ROOT / ".env")
NAME = sys.argv[1] if len(sys.argv) > 1 else "fit-reason-agent"
# Only what the app needs at runtime. The Supabase secret key and demo passwords never leave this machine.
SECRETS = ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_DB_URL", "GROQ_API_KEY"]
VARIABLES = ["LLM_PROVIDER", "FAST_MODEL", "STRONG_MODEL", "INR_PER_USD"]
SPACE_README = """---
title: Fit-Reason Agent
emoji: 🧵
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Internal pilot for Dhaga & Co. (sample data)
---

Fit-Reason Agent: internal pilot for Dhaga & Co. Sign-in required. Sample data only; nothing is sent to customers.
"""

api = HfApi(token=ENV["HF_TOKEN"])
repo_id = f"{api.whoami()['name']}/{NAME}"
api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
for key in SECRETS:
    api.add_space_secret(repo_id, key, ENV[key])
for key in VARIABLES:
    api.add_space_variable(repo_id, key, ENV[key])
api.upload_folder(
    repo_id=repo_id, repo_type="space", folder_path=str(ROOT),
    allow_patterns=["app.py", "requirements.txt", "Dockerfile", ".dockerignore", ".streamlit/config.toml",
                    "core/**/*.py", "core/prompts/*.md", "views/*.py", "db/*.sql", "scripts/*.py"],
    commit_message="Deploy Fit-Reason Agent",
)
api.upload_file(path_or_fileobj=SPACE_README.encode(), path_in_repo="README.md", repo_id=repo_id, repo_type="space")
print("Space:", f"https://huggingface.co/spaces/{repo_id}")
print("App URL:", f"https://{repo_id.replace('/', '-').replace('_', '-').lower()}.hf.space")
