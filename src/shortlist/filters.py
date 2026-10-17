"""Cheap checks that rule a job out before any model looks at it.

Titles say seniority ("Senior", "Staff", "SDE III"); descriptions say how many
years they want ("3+ years", "2-4 years of experience"). Both are guessed with
patterns, and a guess can be wrong, so these only rule out the clear cases.
"""
import re

TOO_SENIOR = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|leader|manager|director|head|architect|vp|vice president|"
    r"distinguished|fellow|chief)\b"
    r"|\b(?:sde|swe|engineer|developer)\s*(?:iii|iv|v|3|4|5)\b"
    r"|\b[LE][5-9]\b",
    re.I,
)
NOT_A_JOB = re.compile(r"\b(intern|internship|apprentice|trainee)\b", re.I)

# "Engineer" in the title, but not software or AI engineering. Users can replace this list.
OFF_TRACK = (r"support|field|sales|solutions|customer|success|demo|deployment strategist|"
             r"threat|hardware|chip|soc|asic|fpga|silicon|electrical|mechanical|data cent(er|re)|"
             r"technical writ|documentation|content|people systems|workplace|it engineer|network engineer")

_NUM = r"(\d{1,2})"
# "3+ years", "4–6 years of building ...", "(at least 8 years)". Posts word it every way,
# so any "N years" counts unless it's about the company rather than the candidate.
YEARS = re.compile(
    rf"\b{_NUM}\s*(?:\+|plus)?\s*(?:(?:-|–|—|to)\s*{_NUM}\s*)?\+?\s*(?:years?|yrs?)\b"
    r"(?!\s*(?:ago|old|of (?:runway|history|growth|operations?)|in business|running))",
    re.I,
)
_ABOUT_THE_COMPANY = re.compile(r"(past|last|founded|since|around for|over the)\W*$", re.I)


def years_asked(description: str) -> int | None:
    """The smallest minimum the post asks for. "3+ years" and "3-5 years" both mean 3.
    The smallest, because posts list nice-to-haves with bigger numbers."""
    text = description or ""
    found = []
    for m in YEARS.finditer(text):
        if _ABOUT_THE_COMPANY.search(text[max(0, m.start() - 20):m.start()]):
            continue
        found.append(int(m.group(1)))
    found = [n for n in found if n <= 15]  # "25 years of company history" isn't a requirement
    return min(found) if found else None


def rule_out(title: str, description: str, max_years: int, internships: bool = False,
             off_track: str = OFF_TRACK) -> str | None:
    """Why the job is out for this user, or None if it's still in."""
    if TOO_SENIOR.search(title):
        return "senior title"
    if off_track and re.search(rf"\b({off_track})", title, re.I):
        return "off-track role"
    if not internships and NOT_A_JOB.search(title):
        return "internship"
    asked = years_asked(description)
    if asked is not None and asked > max_years:
        return f"asks for {asked}+ years"
    return None
