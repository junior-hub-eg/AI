"""The playground's automatic checks must all pass against the real app (fake models)."""

import httpx
import pytest

from playground.api import DiscoveryApi
from playground.checks import build_checks, run_checks
from playground.sample_data import TRACKS
from tests.conftest import make_settings, sign


@pytest.fixture
def api_via_testclient(monkeypatch, client):
    def fake_request(method, url, json=None, headers=None, timeout=None):
        response = client.request(method, url.replace("http://test", ""), json=json, headers=headers)
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    monkeypatch.setattr(httpx, "request", fake_request)
    return DiscoveryApi("http://test")


def test_all_playground_checks_pass(api_via_testclient):
    rows = run_checks(api_via_testclient, build_checks(TRACKS, 8, auth_enabled=False))
    assert [r for r in rows if r["result"] != "PASS"] == []
    assert len(rows) >= 12


def test_auth_check_passes_when_auth_is_enabled(monkeypatch, rsa_pair):
    from fastapi.testclient import TestClient

    from app.main import create_app

    private, public = rsa_pair
    with TestClient(create_app(make_settings(auth_disabled=False, jwt_public_key=public))) as c:
        monkeypatch.setattr(
            httpx,
            "request",
            lambda method, url, json=None, headers=None, timeout=None: (
                lambda r: httpx.Response(r.status_code, content=r.content, headers=r.headers)
            )(c.request(method, url.replace("http://test", ""), json=json, headers=headers)),
        )
        api = DiscoveryApi("http://test", token=sign(private))
        rows = run_checks(api, build_checks(TRACKS, 8, auth_enabled=True))
    assert all(r["result"] == "PASS" for r in rows)
    assert any("Auth" in r["check"] for r in rows)
