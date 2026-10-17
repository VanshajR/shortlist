from shortlist.rank import _clean, _title_key, candidate_summary

PROFILE = {
    "profile": {"headline": "Software Engineer | AI Systems"},
    "education": [{"degree": "B.E. Computer Science", "institution": "TIET", "end": "2026-07", "score": "CGPA 9.00/10"}],
    "experience": [
        {"org": "DXFactor", "role": "Software Engineer Intern", "kind": "work", "start": "2026-02", "end": "2026-06"},
        {"org": "TICC", "role": "Technical Lead", "kind": "leadership", "start": "2024-05", "end": "2025-12"},
    ],
}


def test_the_judge_is_told_plainly_where_the_candidate_is():
    summary = candidate_summary(PROFILE, today="2026-10")
    assert "graduated Jul 2026" in summary and "CGPA 9.00/10" in summary
    assert "Software Engineer Intern at DXFactor (Feb 2026 to Jun 2026)" in summary
    assert "new graduate" in summary and "TICC" not in summary


def test_before_graduation_it_says_graduating():
    assert "graduating Jul 2026" in candidate_summary(PROFILE, today="2026-03")


def test_the_same_role_in_different_cities_is_one_role():
    assert _title_key("Software Engineer (Bengaluru)") == _title_key("Software Engineer - Pune") == "software engineer"


def test_a_sloppy_verdict_is_brought_into_range():
    assert _clean({"fit": "6", "verdict": "skip"})["verdict"] == "maybe"  # the score decides
    assert _clean({"fit": "11", "verdict": "definitely", "gaps": ["a", "b", "c", "d"]}) == {
        "fit": 10, "verdict": "apply", "why": "", "gaps": ["a", "b", "c"],
        "years_required": None, "open_to_india": None}
    assert _clean({"fit": None})["verdict"] == "skip"
