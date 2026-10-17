"""How well does search find the right experience for a job? Each case is a
job-description-style query and the highlights a good match must surface.

    python evals/retrieval.py

Reports hit@5 (an expected highlight is in the top five) and MRR (how high the
first one ranks), against the first user in DATABASE_URL. Run it after changing
the embedding model or how highlights are built, and compare.
"""
import json
import pathlib

from shortlist import db, embeddings, env, retrieve

HERE = pathlib.Path(__file__).parent


def main() -> None:
    env.load()
    cases = json.loads((HERE / "retrieval.json").read_text(encoding="utf-8"))
    with db.connect() as conn:
        user = conn.execute("select id from users order by id limit 1").fetchone()["id"]
        hits, reciprocal = 0, 0.0
        for case in cases:
            ranked = [h["id"] for h in retrieve.search(conn, user, case["query"], k=10)]
            first = next((i for i, hid in enumerate(ranked) if hid in case["expect"]), None)
            hit = first is not None and first < 5
            hits += hit
            reciprocal += 1 / (first + 1) if first is not None else 0
            print(f"{'PASS' if hit else 'MISS'} {case['id']:<24} first match at {'-' if first is None else first + 1}"
                  + ("" if hit else f"   got: {', '.join(ranked[:3])}"))
    n = len(cases)
    print(f"\n{embeddings.model().label}: hit@5 {hits}/{n} ({hits / n:.0%}), MRR {reciprocal / n:.2f}")


if __name__ == "__main__":
    main()
