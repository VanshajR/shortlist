"""Turn messy location strings into something we can filter on.

Postings say "Gurgaon", "Gurugram", "GGN", "Delhi NCR", "Bengaluru, KA, India"
and mean overlapping things. Getting this wrong silently drops good jobs.
"""
import re

from .models import Job

# alias -> canonical city
CITY_ALIASES = {
    "gurgaon": "Gurugram",
    "gurugram": "Gurugram",
    "noida": "Noida",
    "greater noida": "Noida",
    "new delhi": "Delhi",
    "delhi": "Delhi",
    "ghaziabad": "Ghaziabad",
    "faridabad": "Faridabad",
    "pune": "Pune",
    "hyderabad": "Hyderabad",
    "secunderabad": "Hyderabad",
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "mumbai": "Mumbai",
    "navi mumbai": "Mumbai",
    "chennai": "Chennai",
    "kolkata": "Kolkata",
    "ahmedabad": "Ahmedabad",
    "chandigarh": "Chandigarh",
    "mohali": "Chandigarh",
    "jaipur": "Jaipur",
}

NCR = {"Delhi", "Gurugram", "Noida", "Ghaziabad", "Faridabad"}

_REMOTE = re.compile(r"\b(remote|work from home|wfh|anywhere)\b", re.I)
_NCR = re.compile(r"\b(delhi[- ]ncr|ncr)\b", re.I)
# "IN" only as an uppercase country code, otherwise it matches the word "in"
_INDIA = re.compile(r"(?i:\bindia\b)|\bIN\b")

# longest aliases first so "greater noida" wins over "noida"
_ALIAS_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, CITY_ALIASES), key=len, reverse=True)) + r")\b",
    re.I,
)


def parse_location(raw: str) -> tuple[list[str], bool, bool]:
    """Return (cities, remote, in_india) for a raw location string."""
    # take "Delhi NCR" out first so its "Delhi" isn't read as the city
    mentions_ncr = bool(_NCR.search(raw))
    rest = _NCR.sub(" ", raw)

    cities = []
    for m in _ALIAS_RE.finditer(rest):
        city = CITY_ALIASES[m.group(1).lower()]
        if city not in cities:
            cities.append(city)

    # "Delhi NCR" with no specific city: treat it as all of NCR
    if mentions_ncr and not cities:
        cities = sorted(NCR)

    remote = bool(_REMOTE.search(raw))
    in_india = bool(cities) or bool(_INDIA.search(raw))
    return cities, remote, in_india


def normalize(job: Job) -> Job:
    job.cities, job.remote, job.in_india = parse_location(job.location_raw)
    return job
