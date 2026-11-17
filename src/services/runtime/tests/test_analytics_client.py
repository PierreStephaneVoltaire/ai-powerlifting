import httpx

from services.runtime import analytics_client
from services.runtime.storage_scope import current_athlete, current_person


def test_domain_call_forwards_authenticated_scope(monkeypatch):
    requests = []

    def post(url, **kwargs):
        requests.append((url, kwargs))
        return httpx.Response(200, json={"entries": []}, request=httpx.Request("POST", url))

    monkeypatch.setattr(analytics_client.httpx, "post", post)
    person = current_person.set("person-a")
    athlete = current_athlete.set("athlete-a")
    try:
        assert analytics_client.call("max_history_get", {"pk": "athlete-a"}, domain="performance") == {"entries": []}
    finally:
        current_person.reset(person)
        current_athlete.reset(athlete)
    url, request = requests[0]
    assert url.endswith("/operations/max_history_get") and "pl-performance" in url
    assert request["headers"]["X-Person-Pk"] == "person-a"
    assert request["headers"]["X-Athlete-Pk"] == "athlete-a"
