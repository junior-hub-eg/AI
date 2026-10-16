from __future__ import annotations

import base64
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

TRACKS = [
    {"code": "FRONTEND", "name": "Frontend", "profile": "Builds what people see and click."},
    {"code": "BACKEND", "name": "Backend", "profile": "Builds the hidden engine of apps."},
    {"code": "UIUX", "name": "UI/UX", "profile": "Designs how apps look and feel."},
    {"code": "DATA", "name": "Data", "profile": "Finds patterns in numbers."},
]


def make_settings(**overrides) -> Settings:
    base = {"_env_file": None, "app_env": "test", "fake_models": True, "auth_disabled": True}
    return Settings(**{**base, **overrides})


@pytest.fixture
def client():
    with TestClient(create_app(make_settings())) as c:
        yield c


@pytest.fixture(scope="session")
def rsa_pair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    private_pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return private_pem, public_pem


def sign(private_pem: str, *, aud: str = "discovery-ai", exp_in: int = 300) -> str:
    now = int(time.time())
    return jwt.encode({"aud": aud, "iat": now, "exp": now + exp_in}, private_pem, algorithm="RS256")


def turn_body(**overrides) -> dict:
    body = {
        "interview_id": "iv_1",
        "student_ref": "stu_1",
        "grade": 8,
        "tracks": TRACKS,
        "history": [],
        "answer": None,
        "max_questions": 10,
        "speak": True,
    }
    return {**body, **overrides}


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()
