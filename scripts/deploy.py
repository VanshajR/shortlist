"""Deploy the bot to Vercel and point Telegram at it.

    python scripts/deploy.py

Reads VERCEL_TOKEN and the bot's secrets from .env, stores the secrets as Vercel
environment variables (never in the upload), deploys a clean copy of the app and
sets the Telegram webhook to it. The copy has no git metadata: Vercel's Hobby
plan blocks deploys whose commit author it can't match to the account.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from shortlist import env  # noqa: E402
from shortlist.telegram import Telegram  # noqa: E402

PROJECT = "shortlist-bot"
SHIP = ["index.py", "src", "vercel.json", "requirements.txt", ".python-version", ".vercelignore"]
SECRETS = ["DATABASE_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET", "GEMINI_API_KEY",
           "SHORTLIST_EMBEDDINGS", "OPENAI_API_KEY", "OLLAMA_HOST"]
VERCEL = ["npx", "--yes", "vercel@64.4.0"]


def vercel(args: list[str], cwd: pathlib.Path, token: str) -> str:
    out = subprocess.run([*VERCEL, *args, "--token", token], cwd=cwd, capture_output=True, text=True,
                         shell=(shutil.which("npx") or "").lower().endswith(".cmd"))
    if out.returncode:
        raise SystemExit(f"vercel {args[0]} failed:\n{out.stderr[-2000:]}")
    return out.stdout + out.stderr


def api(token: str, project: dict, path: str, params: dict | None = None, **kw) -> httpx.Response:
    # one params dict: httpx replaces a query string already in the URL with `params`
    params = dict(params or {})
    if project.get("orgId", "").startswith("team_"):
        params["teamId"] = project["orgId"]
    return httpx.request(kw.pop("method", "GET"), f"https://api.vercel.com{path}", params=params,
                         headers={"Authorization": f"Bearer {token}"}, timeout=30, **kw)


def main() -> None:
    env.load()
    import os
    token = os.environ["VERCEL_TOKEN"]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        stage = pathlib.Path(tmp) / PROJECT
        stage.mkdir()
        for name in SHIP:
            src = ROOT / name
            if src.is_dir():
                shutil.copytree(src, stage / name, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
            else:
                shutil.copy2(src, stage / name)
        if (ROOT / ".vercel").exists():
            shutil.copytree(ROOT / ".vercel", stage / ".vercel")
        else:
            vercel(["link", "--yes", "--project", PROJECT], stage, token)
            shutil.copytree(stage / ".vercel", ROOT / ".vercel")
        project = json.loads((stage / ".vercel" / "project.json").read_text())

        for key in SECRETS:
            if os.environ.get(key):
                r = api(token, project, f"/v10/projects/{project['projectId']}/env", {"upsert": "true"}, method="POST",
                        json={"key": key, "value": os.environ[key], "type": "encrypted", "target": ["production"]})
                if r.status_code >= 300:
                    raise SystemExit(f"setting {key} failed: {r.status_code} {r.text[:200]}")
        vercel(["deploy", "--prod", "--yes"], stage, token)

    aliases = api(token, project, f"/v9/projects/{project['projectId']}").json()["targets"]["production"]["alias"]
    url = "https://" + min(aliases, key=len)  # the stable, shortest one
    health = httpx.get(f"{url}/health", timeout=60)
    if health.status_code != 200:
        raise SystemExit(f"deployed, but {url}/health answered {health.status_code}")

    tg = Telegram()
    tg.call("setWebhook", url=f"{url}/telegram", secret_token=os.environ["TELEGRAM_WEBHOOK_SECRET"],
            allowed_updates=["message", "callback_query"], drop_pending_updates=False)
    tg.call("setMyCommands", commands=[
        {"command": "today", "description": "Your current matches"},
        {"command": "search", "description": "Look for jobs"},
        {"command": "prefs", "description": "What it filters on, and how to change it"},
        {"command": "help", "description": "How it works"}])
    info = tg.call("getWebhookInfo")
    print(f"deployed: {url}\nwebhook:  {info['url']}  (pending {info.get('pending_update_count', 0)})")


if __name__ == "__main__":
    main()
