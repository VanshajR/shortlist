"""Choose what goes on a resume for one job. Selection only: every line comes from the
profile as written (a highlight or one of its pre-written alternatives), so a tailored
resume can't claim anything the profile doesn't.

The profile's rules, which this enforces:
- experience with on_resume false never appears; "optional" only if there's room
- highlights that `overlap` cover the same ground, so at most one of them is used
- no action verb starts two bullets
- skills are reordered and trimmed per job, never added
"""
import re
from dataclasses import dataclass, field

BULLETS = {"experience": 4, "project": 2}   # most bullets per role / project
PROJECTS = 4                               # flagship projects shown, at most
MIN_PROJECTS = 3
SKILLS_PER_GROUP = 6
METRIC_BONUS = 0.03  # embedding similarities sit within ~0.1 of each other, so this nudges, not overrides
CORE_SKILLS = ("Languages", "Backend", "AI Systems", "AI/ML", "Cloud", "Databases")


@dataclass
class Bullet:
    id: str            # "experience:dxfactor:rag"
    text: str          # with **bold** metrics, as the profile writes it
    score: float

    @property
    def verb(self) -> str:
        word = re.sub(r"[^a-z]", "", self.text.split()[0].lower()) if self.text.split() else ""
        return word


@dataclass
class Entry:
    kind: str          # experience | project
    key: str           # dxfactor, ev-digital-twin-platform
    data: dict         # the profile's entry
    bullets: list[Bullet] = field(default_factory=list)
    optional: bool = False

    @property
    def score(self) -> float:
        return max((b.score for b in self.bullets), default=0.0)


def choose(profile: dict, scores: dict[str, float] | None = None, job_text: str = "") -> dict:
    """What the resume shows. `scores` maps highlight ids to closeness to the job (0-1);
    without them (a general resume) the profile's own order decides."""
    scores = scores or _profile_order(profile)
    used_verbs: set[str] = set()

    def rank(kind, entry_id, highlights):
        # relevance decides; a measured result (a **bold** metric) breaks near-ties,
        # because a recruiter skimming the page looks for numbers
        order = {h["id"]: i for i, h in enumerate(highlights)}
        weight = lambda h: scores.get(f"{kind}:{entry_id}:{h['id']}", 0.0) + (METRIC_BONUS if "**" in h["text"] else 0)
        return sorted(highlights, key=lambda h: (-weight(h), order[h["id"]]))

    def pick(kind, entry_id, highlights, limit):
        taken, skip = [], set()
        for h in rank(kind, entry_id, highlights):
            if h["id"] in skip or len(taken) == limit:
                continue
            for text in [h["text"], *h.get("alts", [])]:   # the main wording, then its alternatives
                b = Bullet(f"{kind}:{entry_id}:{h['id']}", text, scores.get(f"{kind}:{entry_id}:{h['id']}", 0.0))
                if b.verb and b.verb not in used_verbs:
                    used_verbs.add(b.verb)
                    taken.append(b)
                    skip.update(h.get("overlaps", []))
                    skip.update(o["id"] for o in highlights if h["id"] in o.get("overlaps", []))
                    break
        return taken

    # work first: it's on every resume, so it claims its verbs first
    experience = []
    for e in profile["experience"]:
        flag = e.get("on_resume", True)
        if flag is False or not e.get("highlights"):
            continue
        experience.append(Entry("experience", e["id"], e, pick("experience", e["id"], e["highlights"], BULLETS["experience"]),
                                optional=flag == "optional"))

    candidates = [p for p in profile["projects"] if p["tier"] == "flagship" and p.get("highlights")
                  and p.get("status") != "in-progress"]
    best = lambda p: max((scores.get(f"project:{p['slug']}:{h['id']}", 0.0) for h in p["highlights"]), default=0.0)
    if scores:
        candidates.sort(key=best, reverse=True)
    projects = [Entry("project", p["slug"], p, pick("project", p["slug"], p["highlights"], BULLETS["project"]))
                for p in candidates[:PROJECTS]]

    return {"experience": experience, "projects": projects, "skills": skills_for(profile, job_text),
            "education": profile.get("education", [])}


def _profile_order(profile: dict) -> dict[str, float]:
    """Scores for a resume with no job: the profile's own order, work above projects."""
    scores = {}
    for kind, entries, base in (("experience", profile["experience"], 1.0), ("project", profile["projects"], 0.5)):
        for e in entries:
            key = e["id"] if kind == "experience" else e["slug"]
            for i, h in enumerate(e.get("highlights", [])):
                scores[f"{kind}:{key}:{h['id']}"] = base - 0.01 * i
    return scores


def skills_for(profile: dict, job_text: str) -> list[tuple[str, list[str]]]:
    """A few skills per group, ones the job mentions first. Only the core groups appear,
    plus any other group the job asks for (Frontend, Testing). Nothing is ever added."""
    text = job_text.lower()
    mentioned = lambda s: bool(re.search(rf"(?<![\w+#]){re.escape(s.lower())}(?![\w+#])", text))
    out = []
    for group, items in profile.get("skills", {}).get("groups", {}).items():
        hits = [s for s in items if mentioned(s)]
        if group not in CORE_SKILLS and not hits:
            continue
        out.append((group, (hits + [s for s in items if s not in hits])[:SKILLS_PER_GROUP]))
    return out


def trim(selection: dict) -> bool:
    """Remove the least valuable thing that can go, to get back to one page. False when
    nothing more can be cut. Work experience is cut last: in order, optional entries,
    a fourth project, projects' second bullets, work bullets past the second, a third
    project, then work bullets past the first."""
    for entry in reversed(selection["experience"]):
        if entry.optional:
            selection["experience"].remove(entry)
            return True
    if len(selection["projects"]) > MIN_PROJECTS:
        selection["projects"].pop()
        return True
    for entries, keep in ((selection["projects"], 1), (selection["experience"], 2)):
        if _drop_weakest(entries, keep):
            return True
    if len(selection["projects"]) > 2:
        selection["projects"].pop()
        return True
    return _drop_weakest(selection["experience"], 1)


def _drop_weakest(entries: list[Entry], keep: int) -> bool:
    shown = [(b.score, e, b) for e in entries for b in e.bullets if len(e.bullets) > keep]
    if not shown:
        return False
    _, entry, bullet = min(shown, key=lambda t: t[0])
    entry.bullets.remove(bullet)
    return True
