from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings, sign, turn_body


def secured_client(public_pem: str) -> TestClient:
    return TestClient(create_app(make_settings(auth_disabled=False, jwt_public_key=public_pem)))


def test_valid_token_is_accepted(rsa_pair):
    private, public = rsa_pair
    with secured_client(public) as c:
        r = c.post(
            "/v1/discovery/turns", json=turn_body(), headers={"Authorization": f"Bearer {sign(private)}"}
        )
    assert r.status_code == 200


def test_missing_token_is_401(rsa_pair):
    with secured_client(rsa_pair[1]) as c:
        r = c.post("/v1/discovery/turns", json=turn_body())
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"
    assert r.headers["www-authenticate"] == "Bearer"


def test_wrong_audience_expired_and_garbage_are_401(rsa_pair):
    private, public = rsa_pair
    bad = [sign(private, aud="someone-else"), sign(private, exp_in=-3600), "garbage"]
    with secured_client(public) as c:
        for token in bad:
            r = c.post("/v1/discovery/turns", json=turn_body(), headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 401


def test_token_signed_by_another_key_is_401(rsa_pair):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    with secured_client(rsa_pair[1]) as c:
        r = c.post(
            "/v1/discovery/turns", json=turn_body(), headers={"Authorization": f"Bearer {sign(other_pem)}"}
        )
    assert r.status_code == 401


def test_auth_is_checked_before_validation(rsa_pair):
    with secured_client(rsa_pair[1]) as c:
        r = c.post("/v1/discovery/turns", json={"nonsense": True})
    assert r.status_code == 401
