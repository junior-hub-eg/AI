import json
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import main
from app.assistant import Assistant
from app.config import Settings
from app.fake_llm import FakeChatModel
from tests.conftest import load_context

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
PUBLIC = KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def token(audience="assistant-ai", issuer="JuniorHub.Api", lifetime=300, key=PRIVATE):
    now = int(time.time())
    return jwt.encode({"aud": audience, "iss": issuer, "iat": now, "nbf": now, "exp": now + lifetime, "jti": uuid.uuid4().hex},
                      key, algorithm="RS256")


def body(message="الدرس الجاي إيه؟"):
    return {"conversation_id": str(uuid.uuid4()), "student_ref": str(uuid.uuid4()), "message": message,
            "history": [], "context": load_context("frontend_beginner")}


@pytest.fixture
def client(monkeypatch):
    settings = Settings(llm_model="fake", auth_public_key_pem=PUBLIC)
    main.app.state.assistant = Assistant(FakeChatModel(), settings)
    yield TestClient(main.app)
    del main.app.state.assistant


def post(client, payload, bearer=None):
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    return client.post("/v1/assistant/replies", content=json.dumps(payload), headers={**headers, "Content-Type": "application/json"})


def test_a_signed_request_gets_a_reply(client):
    response = post(client, body(), token())
    assert response.status_code == 200
    data = response.json()
    assert data["reply"].startswith("(تجربة)") and data["meta"]["prompt_version"] == "assistant@v1"


@pytest.mark.parametrize("bad", [None, "not-a-jwt", "WRONG_AUD", "WRONG_ISS", "EXPIRED", "OTHER_KEY"])
def test_bad_tokens_are_rejected_before_the_body_is_read(client, bad):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    value = {"WRONG_AUD": token(audience="discovery-ai"), "WRONG_ISS": token(issuer="someone"),
             "EXPIRED": token(lifetime=-120), "OTHER_KEY": token(key=other)}.get(bad, bad)
    response = post(client, {"not": "even valid"}, value)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_invalid_body_names_the_fields_without_echoing_the_message(client):
    payload = body("x" * 1001)
    response = post(client, payload, token())
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "INVALID_REQUEST" and "message" in error["message"] and "xxxx" not in error["message"]


def test_a_provider_failure_is_503(client, monkeypatch):
    async def boom(request):
        raise ConnectionError("provider down")

    monkeypatch.setattr(main.app.state.assistant, "reply_with_trace", boom)
    response = post(client, body(), token())
    assert response.status_code == 503 and response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


def test_health(client):
    data = client.get("/health").json()
    assert data["status"] == "ok" and data["catalog_version"]


@pytest.fixture
def dev_client():
    settings = Settings(llm_model="fake", auth_public_key_pem=PUBLIC, dev_endpoints=True)
    main.app.state.assistant = Assistant(FakeChatModel(), settings)
    yield TestClient(main.app)
    del main.app.state.assistant


def test_dev_endpoints_are_off_by_default(client):
    assert client.get("/v1/dev/personas").status_code == 404
    assert client.post("/v1/dev/chat", json={"persona": "new_student", "message": "hi"}).status_code == 404


def test_dev_chat_as_a_mock_student(dev_client):
    assert "frontend_beginner" in dev_client.get("/v1/dev/personas").json()
    assert dev_client.get("/v1/dev/personas/new_student").json()["learning"] is None
    response = dev_client.post("/v1/dev/chat", json={"persona": "frontend_beginner", "message": "الدرس الجاي إيه؟"})
    assert response.status_code == 200 and response.json()["reply"].startswith("(تجربة)")


def test_dev_personas_cannot_read_other_files(dev_client):
    assert dev_client.get("/v1/dev/personas/..%2F..%2Fapp%2Fconfig").status_code == 404
    assert dev_client.post("/v1/dev/chat", json={"persona": "../../data/catalog", "message": "hi"}).status_code == 404


def test_the_openapi_schema_documents_the_request_body(client):
    schema = client.get("/openapi.json").json()
    body = schema["paths"]["/v1/assistant/replies"]["post"]["requestBody"]
    assert "ReplyRequest" in json.dumps(body)


def test_the_home_page_is_the_test_chat_only_with_dev_endpoints(client):
    assert client.get("/").json()["docs"] == "/docs"


def test_the_test_chat_page_is_served_in_dev(dev_client):
    page = dev_client.get("/")
    assert page.status_code == 200 and "/v1/dev/chat" in page.text


def test_dev_chat_shows_the_tools_used(dev_client):
    data = dev_client.post("/v1/dev/chat", json={"persona": "frontend_beginner", "message": "مين معايا في الفريق؟"}).json()
    assert data["debug"]["tools"] == ["get_my_squad"]
    # What the bot saw, to check the reply against: the snapshot and each tool's data.
    assert "teammates Mohammed (Frontend), Nour (UIUX), Youssef (Testing)" in data["debug"]["snapshot"]
    step = data["debug"]["steps"][0]
    assert step["tool"] == "get_my_squad" and step["result"]["name"] == "Code Hunters"


def test_provider_keys_in_dotenv_reach_the_environment(tmp_path, monkeypatch):
    from app import config
    (tmp_path / ".env").write_text("LLM_MODEL=cohere:command-a-03-2025\nJH_TEST_PROVIDER_KEY=abc\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JH_TEST_PROVIDER_KEY", raising=False)
    config.get_settings.cache_clear()
    try:
        assert config.get_settings().llm_model == "cohere:command-a-03-2025"
        import os
        assert os.environ["JH_TEST_PROVIDER_KEY"] == "abc"
    finally:
        config.get_settings.cache_clear()
        os.environ.pop("JH_TEST_PROVIDER_KEY", None)


def test_a_model_that_cannot_start_is_a_503_not_a_crash(monkeypatch):
    settings = Settings(llm_model="cohere:command-a-03-2025", dev_endpoints=True, auth_disabled=True)
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    monkeypatch.delenv("CO_API_KEY", raising=False)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    if hasattr(main.app.state, "assistant"):
        del main.app.state.assistant
    client = TestClient(main.app)
    assert client.get("/").status_code == 200
    response = client.post("/v1/dev/chat", json={"persona": "new_student", "message": "hi"})
    assert response.status_code == 503 and "ApiError" in response.json()["error"]["message"]
