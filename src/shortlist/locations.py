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

# For remote jobs: is it open to someone in India? US companies often write just
# "Remote" and mean the US, so a bare "Remote" is "unclear" and the judge reads the post.
_GLOBAL = re.compile(r"\b(anywhere|worldwide|global|apac|asia|asia[- ]pacific)\b", re.I)
_FOREIGN = re.compile(
    r"\b(us|usa|united states|u\.s\.|americas?|north america|canada|mexico|brazil|latam|"
    r"uk|united kingdom|ireland|europe|emea|eu|germany|france|spain|netherlands|poland|portugal|"
    r"australia|new zealand|japan|singapore|philippines|israel|uae|dubai|"
    # "San Francisco (Remote)" names a city, not a country
    r"san francisco|sf|bay area|new york|nyc|seattle|mountain view|palo alto|sunnyvale|menlo park|"
    r"los angeles|boston|austin|chicago|denver|washington|toronto|vancouver|london|dublin|berlin|"
    r"munich|amsterdam|paris|zurich|stockholm|tel aviv|sydney|melbourne|tokyo|seoul)\b"
    r"|,\s*(?:CA|NY|WA|TX|MA|IL|CO|GA|FL|OR|VA|NC|PA|NJ|AZ|MN|UT)\b",
    re.I,
)

# longest aliases first so "greater noida" wins over "noida"
_ALIAS_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, CITY_ALIASES), key=len, reverse=True)) + r")\b",
    re.I,
)


def remote_scope(raw: str, remote: bool, in_india: bool) -> str | None:
    """Who a remote job is open to: 'india', 'global', 'foreign' or 'unclear'. None if not remote."""
    if not remote:
        return None
    if in_india:
        return "india"
    if _GLOBAL.search(raw):
        return "global"
    if _FOREIGN.search(raw):
        return "foreign"
    return "unclear"


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
    job.remote_scope = remote_scope(job.location_raw, job.remote, job.in_india)
    return job
