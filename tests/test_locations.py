import pytest

from shortlist.locations import NCR, parse_location


@pytest.mark.parametrize(
    "raw, cities",
    [
        ("Gurgaon, India", ["Gurugram"]),
        ("Gurugram, Haryana", ["Gurugram"]),
        ("Bangalore, KA", ["Bengaluru"]),
        ("Bengaluru; Hyderabad", ["Bengaluru", "Hyderabad"]),
        ("Greater Noida", ["Noida"]),
        ("New Delhi", ["Delhi"]),
    ],
)
def test_city_aliases(raw, cities):
    assert parse_location(raw)[0] == cities


def test_delhi_ncr_expands_to_whole_region():
    cities, _, in_india = parse_location("Delhi NCR")
    assert set(cities) == NCR
    assert in_india


def test_specific_ncr_city_is_not_expanded():
    assert parse_location("Noida, Delhi NCR")[0] == ["Noida"]


def test_remote():
    _, remote, in_india = parse_location("Remote - India")
    assert remote and in_india


def test_foreign_location():
    cities, remote, in_india = parse_location("San Francisco, CA")
    assert cities == [] and not remote and not in_india


def test_pune_inside_a_word_does_not_match():
    assert parse_location("Punekar Street, London")[0] == []


@pytest.mark.parametrize(
    "raw, scope",
    [
        ("Remote - India", "india"),
        ("Remote, Bengaluru", "india"),
        ("Remote (Anywhere)", "global"),
        ("Remote - APAC", "global"),
        ("Remote - US", "foreign"),
        ("Remote, San Francisco, CA", "foreign"),
        ("Remote - EMEA", "foreign"),
        ("San Francisco, Mountain View (Remote)", "foreign"),
        ("New York City (Remote)", "foreign"),
        ("Remote", "unclear"),
        ("Pune", None),
    ],
)
def test_who_a_remote_job_is_open_to(raw, scope):
    from shortlist.locations import remote_scope
    cities, remote, in_india = parse_location(raw)
    assert remote_scope(raw, remote, in_india) == scope
