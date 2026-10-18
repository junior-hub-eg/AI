import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import TRACKS, make_settings


def result_body(n: int = 6, **overrides) -> dict:
    responses = [
        {"order_index": i, "question_text": f"Q{i}?", "transcript": "I like games."} for i in range(1, n + 1)
    ]
    body = {
        "interview_id": "iv_1",
        "student_ref": "stu_1",
        "grade": 8,
        "tracks": TRACKS,
        "responses": responses,
    }
    return {**body, **overrides}


def test_result_has_three_ranked_distinct_tracks(client):
    r = client.post("/v1/discovery/results", json=result_body())
    assert r.status_code == 200
    data = r.json()
    recs = data["recommendations"]
    assert [x["rank"] for x in recs] == [1, 2, 3]
    assert len({x["track_code"] for x in recs}) == 3
    assert [x["match_percent"] for x in recs] == sorted((x["match_percent"] for x in recs), reverse=True)
    assert all(len(x["reason"]) <= 300 for x in recs)
    assert data["summary"] and data["meta"]["prompt_version"] == "discovery_result@v2"


def test_too_few_responses_rejected(client):
    r = client.post("/v1/discovery/results", json=result_body(n=3))
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_fewer_than_three_tracks_rejected(client):
    r = client.post("/v1/discovery/results", json=result_body(tracks=TRACKS[:2]))
    assert r.status_code == 400


def test_duplicate_track_codes_rejected(client):
    r = client.post("/v1/discovery/results", json=result_body(tracks=[TRACKS[0]] * 3))
    assert r.status_code == 400


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_health_endpoints(client, path):
    assert client.get(path).status_code == 200


def test_production_refuses_disabled_auth():
    with pytest.raises(ValueError):
        make_settings(app_env="production", auth_disabled=True, fake_models=False, groq_api_key="gsk_x")


def test_missing_groq_key_gives_clear_message():
    with pytest.raises(ValueError, match="GROQ_API_KEY IS MISSING"):
        make_settings(fake_models=False)


def test_oversized_request_rejected_early():
    app = create_app(make_settings(max_request_bytes=1000))
    with TestClient(app) as c:
        r = c.post("/v1/discovery/turns", content=b"x" * 2000, headers={"content-type": "application/json"})
    assert r.status_code == 413
