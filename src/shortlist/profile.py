"""A user's experience, read from a profile.json in the portfolio's data format
(the same file their site and Axiom read), split into highlights and embedded.

    python -m shortlist.profile                      # sync the first user
    python -m shortlist.profile --url URL --name N   # create or update a user
"""
import argparse
import re

import httpx
import psycopg

from . import db, embeddings, env

BOLD = re.compile(r"\*\*(.+?)\*\*")


def plain(text: str) -> str:
    """Highlights mark metrics as **bold** for the site; the vectors don't need it."""
    return BOLD.sub(r"\1", text).strip()


def highlights_from(profile: dict) -> list[dict]:
    """Every highlight bullet, plus a summary per role and project."""
    found = []

    def add(kind, owner_id, owner, piece_id, text, tags=(), meta=None):
        if text and text.strip():
            found.append({"id": f"{kind}:{owner_id}:{piece_id}", "kind": kind, "owner": owner,
                          "text": plain(text), "tags": list(tags), "meta": meta or {}})

    for e in profile.get("experience", []):
        meta = {"role": e.get("role"), "start": e.get("start"), "end": e.get("end")}
        add("experience", e["id"], e["org"], "summary", e.get("summary"), meta=meta)
        for h in e.get("highlights", []):
            add("experience", e["id"], e["org"], h["id"], h["text"], h.get("tags", []), meta)

    for p in profile.get("projects", []):
        meta = {"tier": p.get("tier"), "tech": p.get("tech", []), "links": p.get("links", {})}
        add("project", p["slug"], p["name"], "summary", p.get("summary"), p.get("areas", []), meta)
        for h in p.get("highlights", []):
            add("project", p["slug"], p["name"], h["id"], h["text"], h.get("tags", []), meta)
    return found


def sync(conn: psycopg.Connection, user_id: int, profile: dict) -> dict:
    """Bring a user's highlights in line with their profile, embedding only new or edited ones."""
    wanted = {h["id"]: h for h in highlights_from(profile)}
    known = {r["id"]: r["text_hash"] for r in conn.execute(
        "select id, text_hash from highlights where user_id = %s", (user_id,))}

    for h in wanted.values():
        h["text_hash"] = embeddings.text_hash(f"{h['owner']}: {h['text']}")
    changed = [h for h in wanted.values() if known.get(h["id"]) != h["text_hash"]]
    if changed:
        # the owner goes in with the text: "Built X" means more as "depthpad: Built X"
        vectors = embeddings.embed([f"{h['owner']}: {h['text']}" for h in changed])
        for h, vector in zip(changed, vectors):
            h["embedding"] = vector

    gone = [hid for hid in known if hid not in wanted]
    with conn.transaction():
        for h in wanted.values():
            conn.execute(
                """insert into highlights (user_id, id, kind, owner, text, tags, meta, text_hash, embedding)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict (user_id, id) do update set
                       kind = excluded.kind, owner = excluded.owner, text = excluded.text,
                       tags = excluded.tags, meta = excluded.meta, text_hash = excluded.text_hash,
                       embedding = coalesce(excluded.embedding, highlights.embedding)""",
                (user_id, h["id"], h["kind"], h["owner"], h["text"], h["tags"],
                 psycopg.types.json.Jsonb(h["meta"]), h["text_hash"], h.get("embedding")),
            )
        if gone:
            conn.execute("delete from highlights where user_id = %s and id = any(%s)", (user_id, gone))
    return {"highlights": len(wanted), "embedded": len(changed), "removed": len(gone)}


def fetch_profile(url: str) -> dict:
    r = httpx.get(url, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="profile.json to read")
    parser.add_argument("--name", help="who it belongs to (creates the user if new)")
    args = parser.parse_args()
    env.load()
    with db.connect() as conn:
        if args.url and args.name:
            user = conn.execute("select id from users where name = %s", (args.name,)).fetchone()
            if user:
                conn.execute("update users set profile_url = %s where id = %s", (args.url, user["id"]))
            else:
                conn.execute("insert into users (name, profile_url) values (%s, %s)", (args.name, args.url))
            conn.commit()
        user = conn.execute("select id, name, profile_url from users order by id limit 1").fetchone()
        if not user or not user["profile_url"]:
            raise SystemExit("no user yet: pass --url and --name")
        result = sync(conn, user["id"], fetch_profile(user["profile_url"]))
        print(f"{user['name']}: {result}")


if __name__ == "__main__":
    main()
