import httpx

from shortlist.sources import workday
from shortlist.sources.workday import WorkdaySource, _india_facet


def test_india_is_found_however_deep_the_site_keeps_it():
    facets = [{"facetParameter": "locationMainGroup", "values": [
        {"facetParameter": "locationHierarchy1", "descriptor": "Asia", "values": [
            {"descriptor": "Japan", "id": "jp"}, {"descriptor": "India", "id": "in-id"}]}]}]
    assert _india_facet(facets) == ("locationHierarchy1", "in-id")


def test_pages_continue_past_the_first_even_though_later_ones_report_no_total(monkeypatch):
    postings = [{"title": f"Software Engineer {i}", "externalPath": f"/job/x_{i}", "postedOn": "Posted Today"}
                for i in range(45)]

    def handler(request):
        if request.method == "POST":
            body = httpx.Request("POST", request.url, content=request.content).read()
            offset = __import__("json").loads(body)["offset"]
            page = {"jobPostings": postings[offset:offset + 20], "total": 45 if offset == 0 else 0}
            if offset == 0:
                page["facets"] = [{"facetParameter": "country", "values": [{"descriptor": "India", "id": "in"}]}]
            return httpx.Response(200, json=page)
        n = request.url.path.rsplit("_", 1)[-1]
        return httpx.Response(200, json={"jobPostingInfo": {
            "title": f"Software Engineer {n}", "jobReqId": f"R{n}", "location": "India, Pune",
            "jobDescription": "<p>Build things</p>", "startDate": "2026-10-01"}})

    real = httpx.Client
    monkeypatch.setattr(workday.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    jobs = WorkdaySource("acme.wd5/careers").fetch()
    assert len(jobs) == 45
    assert jobs[0].company == "acme" and jobs[0].location_raw == "India, Pune" and jobs[0].external_id == "R0"
