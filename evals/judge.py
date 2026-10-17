"""Does the ranking agree with a person about which jobs are worth applying to?

    python evals/judge.py

Runs each rated job in judge_labels.json through the real pipeline (the user's
filters, then the LLM judge, with evidence from their highlights) and compares
the outcome with how they rated it: Y (would apply), M (maybe), N (no).
A filtered-out job counts as N; a judged one is Y at fit 7+, M at 5-6, N below.

Uses the first user in DATABASE_URL for preferences and highlights, and the
models in SHORTLIST_LLM / SHORTLIST_EMBEDDINGS.
"""
import json
import pathlib
import sys

from shortlist import db, env, filters, retrieve
from shortlist.profile import fetch_profile
from shortlist.rank import judge_post, judge_prompt, off_track_for, prefs_for

HERE = pathlib.Path(__file__).parent
SHORT = {"apply": "Y", "maybe": "M", "skip": "N"}


def main() -> None:
    env.load()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cases = json.loads((HERE / "judge_labels.json").read_text(encoding="utf-8"))["cases"]
    with db.connect() as conn:
        user = conn.execute("select * from users order by id limit 1").fetchone()
        prefs = prefs_for(user)
        system = judge_prompt(fetch_profile(user["profile_url"]), prefs)
        rows = []
        for case in cases:
            reason = filters.rule_out(case["title"], case["description"], prefs["max_years"],
                                      prefs["internships"], off_track_for(prefs))
            if reason:
                got, detail = "N", f"filtered: {reason}"
            else:
                evidence = retrieve.search(conn, user["id"], f"{case['title']}\n{case['description'][:3000]}", k=5)
                verdict, model = judge_post(system, case, evidence)
                got, detail = SHORT[verdict["verdict"]], f"fit {verdict['fit']}: {verdict['why'][:110]}"
            rows.append((case, got, detail))
            mark = "  " if got == case["rating"] else "✗ "
            print(f"{mark}{case['rating']} vs {got}  {case['title'][:46]:<46}  {detail}")

    n = len(rows)
    exact = sum(got == c["rating"] for c, got, _ in rows)
    wanted = [got != "N" for c, got, _ in rows if c["rating"] != "N"]   # jobs they'd consider
    shown = [c["rating"] != "N" for c, got, _ in rows if got != "N"]    # jobs the system would show
    recall = sum(wanted) / len(wanted) if wanted else 0
    precision = sum(shown) / len(shown) if shown else 0
    print(f"\nagrees exactly on {exact}/{n} ({exact / n:.0%}); of the {len(wanted)} jobs they'd consider, "
          f"it shows {sum(wanted)} ({recall:.0%}); of the {len(shown)} it shows, {sum(shown)} are ones they'd "
          f"consider ({precision:.0%})")


if __name__ == "__main__":
    main()
