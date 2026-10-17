import pytest

from shortlist.filters import rule_out, years_asked


@pytest.mark.parametrize("title", [
    "Senior Software Engineer", "Sr. Backend Engineer", "Staff ML Engineer", "Engineering Manager",
    "Principal Architect", "SDE III", "Software Engineer 4", "Tech Lead, Platform", "L5 Engineer",
])
def test_senior_titles_are_out(title):
    assert rule_out(title, "", max_years=2) == "senior title"


@pytest.mark.parametrize("title", [
    "Software Engineer", "SDE I", "Software Engineer II", "Associate Software Engineer",
    "AI Engineer, New Grad", "Backend Developer", "Machine Learning Engineer",
])
def test_early_career_titles_stay(title):
    assert rule_out(title, "", max_years=2) is None


@pytest.mark.parametrize("text, years", [
    ("You have 3+ years of experience building APIs.", 3),
    ("2-4 years of professional experience", 2),
    ("At least 5 years’ industry experience", 5),
    ("1 to 3 yrs of experience in Python", 1),
    ("5+ years of experience preferred; 2+ years of experience required", 2),
    ("We've been around for 25 years and have 3 years of runway", None),
    ("Cloud Operations engineer (at least 8 years)", 8),
    ("• 4–6 years of building and operating production backends", 4),
    ("Over the past 10 years we've grown. You bring 2+ years with Go.", 2),
    ("Strong experience with Go", None),
])
def test_years_asked(text, years):
    assert years_asked(text) == years


def test_too_many_years_rules_a_job_out():
    assert rule_out("Software Engineer", "4+ years of experience with Kubernetes", max_years=2) == "asks for 4+ years"
    assert rule_out("Software Engineer", "1+ years of experience", max_years=2) is None


def test_internships_only_when_wanted():
    assert rule_out("Software Engineering Intern", "", max_years=2) == "internship"
    assert rule_out("Software Engineering Intern", "", max_years=2, internships=True) is None


@pytest.mark.parametrize("title", [
    "Dedicated Support Engineer", "Field Engineer", "Solutions Engineer", "SoC Engineer",
    "Content Systems Engineer, Technical Documentation", "People Systems Engineer",
])
def test_engineer_titles_outside_software_and_ai_are_out(title):
    assert rule_out(title, "", max_years=2) == "off-track role"


@pytest.mark.parametrize("title", ["Software Engineer, Model API Platform", "Machine Learning Engineer", "Site Reliability Engineer"])
def test_software_and_ai_titles_are_on_track(title):
    assert rule_out(title, "", max_years=2) is None
