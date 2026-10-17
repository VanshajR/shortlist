import os
import secrets

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException

from .fetch import fetch_all

app = FastAPI(title="shortlist")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/fetch", status_code=202)
def trigger_fetch(background: BackgroundTasks, x_fetch_token: str = Header(default="")):
    expected = os.environ.get("FETCH_TOKEN", "")
    if not expected or not secrets.compare_digest(x_fetch_token, expected):
        raise HTTPException(status_code=401)
    # the deployed app never runs private sources
    background.add_task(fetch_all, include_private=False)
    return {"queued": True}
