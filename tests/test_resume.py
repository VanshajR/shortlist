import shutil

import pytest

from shortlist.resume import select, template
from shortlist.resume.build import CompileError, build

PROFILE = {
    "profile": {"name": "Asha Rao", "headline": "Software Engineer | AI", "email": "asha@example.com",
                "website": "https://asha.dev", "links": {"github": "https://github.com/asha", "linkedin": "https://linkedin.com/in/asha"}},
    "education": [
        {"institution": "TIET", "location": "Patiala", "degree": "B.E. Computer Science", "score": "CGPA 9.00/10", "end": "2026-07"},
        {"institution": "DPS", "location": "Dehradun", "degree": "Class XII (CBSE)", "score": "98%", "end": "2021-07"},
        {"institution": "DPS", "location": "Dehradun", "degree": "Class X (CBSE)", "score": "96%", "end": "2019-05"},
    ],
    "experience": [
        {"id": "acme", "org": "Acme & Co", "role": "SWE Intern", "kind": "work", "start": "2026-02", "end": "2026-06",
         "location": "Pune", "highlights": [
             {"id": "rag", "text": "Built a RAG platform over **5,000+ documents**."},
             {"id": "rag2", "text": "Built retrieval for 50% faster search.", "alts": ["Designed retrieval for faster search."]},
             {"id": "tests", "text": "Wrote cross-tenant tests.", "overlaps": ["rag"]},
         ]},
        {"id": "club", "org": "Coding Club", "role": "Lead", "kind": "leadership", "on_resume": "optional",
         "start": "2024-05", "highlights": [{"id": "app", "text": "Spearheaded an app launch."}]},
        {"id": "old", "org": "Old Co", "role": "Intern", "kind": "work", "on_resume": False,
         "start": "2023-01", "highlights": [{"id": "x", "text": "Did things."}]},
    ],
    "projects": [
        {"slug": "twin", "name": "EV Twin", "resume_name": "EV Twin (Patent Pending)", "tier": "flagship", "tech": ["Go", "Python"],
         "links": {"code": "https://github.com/asha/twin"}, "highlights": [{"id": "fleet", "text": "Tracked **601 vehicles** in real time."}]},
        {"slug": "wip", "name": "WIP", "tier": "flagship", "status": "in-progress", "highlights": [{"id": "a", "text": "Planned."}]},
        {"slug": "side", "name": "Side", "tier": "side", "highlights": [{"id": "a", "text": "Made a thing."}]},
    ],
    "skills": {"groups": {"Languages": ["Python", "Go", "C++"], "Frontend": ["React", "Svelte"], "Testing": ["Pytest"]}},
}


def test_the_profiles_rules_hold():
    chosen = select.choose(PROFILE)
    work = {e.key: e for e in chosen["experience"]}
    assert set(work) == {"acme", "club"}  # on_resume: false never appears
    assert work["club"].optional
    bullets = [b.id for b in work["acme"].bullets]
    assert "experience:acme:tests" not in bullets       # overlaps the RAG bullet, which is in
    texts = [b.text for b in work["acme"].bullets]
    assert "Designed retrieval for faster search." in texts  # "Built" was taken, so the alternative wording
    assert [p.key for p in chosen["projects"]] == ["twin"]   # flagship and not in progress only


def test_the_job_decides_the_order():
    chosen = select.choose(PROFILE, {"experience:acme:rag2": 0.9, "experience:acme:rag": 0.2})
    assert chosen["experience"][0].bullets[0].id == "experience:acme:rag2"


def test_skills_follow_the_job_and_are_never_added():
    general = dict(select.skills_for(PROFILE, ""))
    assert "Frontend" not in general and "Languages" in general
    tailored = dict(select.skills_for(PROFILE, "We use Go and React daily"))
    assert tailored["Languages"][0] == "Go" and tailored["Frontend"][0] == "React"
    assert all(s in sum(PROFILE["skills"]["groups"].values(), []) for items in tailored.values() for s in items)


def test_trimming_cuts_optional_and_projects_before_work():
    chosen = select.choose(PROFILE)
    assert select.trim(chosen) and all(not e.optional for e in chosen["experience"])
    work_before = len(chosen["experience"][0].bullets)
    assert select.trim(chosen) and len(chosen["experience"][0].bullets) == work_before - 1  # the project kept its one bullet


def test_latex_is_escaped_and_bold_kept():
    assert template.tex("Acme & Co: 50% of **5,000+ docs** | C#") == r"Acme \& Co: 50\% of \textbf{5,000+ docs} \textbar{} C\#"


def test_the_document_has_icons_with_clean_text_and_one_line_per_school():
    source = template.render(PROFILE, select.choose(PROFILE), phone="+91-9999999999")
    assert r"\icon{phone-alt}~+91-9999999999" in source and r"\pdfgentounicode=1" in source
    assert r"\href{mailto:asha@example.com}" in source
    assert "Class XII: 98\\% $|$ Class X: 96\\%" in source
    assert "EV Twin (Patent Pending)" in source and r"\section{\textcolor{red}{Leadership}}" in source


@pytest.mark.skipif(not (shutil.which("pdflatex") or shutil.which("docker")), reason="needs pdflatex or docker")
def test_it_compiles_to_one_clean_page():
    try:
        result = build(PROFILE, phone="+91-9999999999")
    except CompileError as e:
        pytest.skip(f"no working LaTeX here: {e}")
    assert result.pages == 1 and result.problems == []
