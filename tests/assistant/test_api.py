import json
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.main import create_app
from assistant.assistant import Assistant
from assistant.config import Settings
from assistant.fake_llm import FakeChatModel
from tests.conftest import make_settings
from tests.assistant.conftest import load_context

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


def make_client(**assistant):
    """The whole AI service app (Discovery and assistant) with the given assistant settings."""
    settings = Settings(_env_file=None, **{"llm_model": "fake", "auth_public_key_pem": PUBLIC, **assistant})
    service = create_app(make_settings(), assistant_settings=settings)
    if settings.llm_model == "fake":
        service.state.assistant = Assistant(FakeChatModel(), settings)
    return TestClient(service)


@pytest.fixture
def client():
    with make_client() as c:
        yield c


def post(client, payload, bearer=None):
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    return client.post("/v1/assistant/replies", content=json.dumps(payload), headers={**headers, "Content-Type": "application/json"})


def test_a_signed_request_gets_a_reply(client):
    response = post(client, body(), token())
    assert response.status_code == 200
    data = response.json()
    assert data["reply"].startswith("(تجربة)") and data["meta"]["prompt_version"] == "assistant@v3"


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

    monkeypatch.setattr(client.app.state.assistant, "reply_with_trace", boom)
    response = post(client, body(), token())
    assert response.status_code == 503 and response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


def test_health(client):
    data = client.get("/assistant/health").json()
    assert data["status"] == "ok" and data["catalog_version"]


@pytest.fixture
def dev_client():
    with make_client(dev_endpoints=True) as c:
        yield c


def test_dev_endpoints_are_off_by_default(client):
    assert client.get("/v1/dev/personas").status_code == 404
    assert client.post("/v1/dev/chat", json={"persona": "new_student", "message": "hi"}).status_code == 404


def test_dev_chat_as_a_mock_student(dev_client):
    assert "frontend_beginner" in dev_client.get("/v1/dev/personas").json()
    assert dev_client.get("/v1/dev/personas/new_student").json()["learning"] is None
    response = dev_client.post("/v1/dev/chat", json={"persona": "frontend_beginner", "message": "الدرس الجاي إيه؟"})
    assert response.status_code == 200 and response.json()["reply"].startswith("(تجربة)")


def test_dev_personas_cannot_read_other_files(dev_client):
    assert dev_client.get("/v1/dev/personas/..%2F..%2Fconfig").status_code == 404
    assert dev_client.post("/v1/dev/chat", json={"persona": "../data/catalog", "message": "hi"}).status_code == 404


def test_the_openapi_schema_documents_the_request_body(client):
    schema = client.get("/openapi.json").json()
    body = schema["paths"]["/v1/assistant/replies"]["post"]["requestBody"]
    assert "ReplyRequest" in json.dumps(body)


def test_the_test_chat_page_is_only_served_with_dev_endpoints(client):
    assert client.get("/assistant/").status_code == 404


def test_the_test_chat_page_is_served_in_dev(dev_client):
    page = dev_client.get("/assistant/")
    assert page.status_code == 200 and "/v1/dev/chat" in page.text


def test_dev_chat_shows_the_tools_used(dev_client):
    data = dev_client.post("/v1/dev/chat", json={"persona": "frontend_beginner", "message": "مين معايا في الفريق؟"}).json()
    assert data["debug"]["tools"] == ["get_my_squad"]
    # What the bot saw, to check the reply against: the snapshot and each tool's data.
    assert "teammates Mohammed (Frontend), Nour (UIUX), Youssef (Testing)" in data["debug"]["snapshot"]
    step = data["debug"]["steps"][0]
    assert step["tool"] == "get_my_squad" and step["result"]["name"] == "Code Hunters"


def test_provider_keys_in_dotenv_reach_the_environment(tmp_path, monkeypatch):
    from assistant import config
    (tmp_path / ".env").write_text("ASSISTANT_LLM_MODEL=cohere:command-a-03-2025\nJH_TEST_PROVIDER_KEY=abc\n", encoding="utf-8")
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
        os.environ.pop("ASSISTANT_LLM_MODEL", None)  # load_dotenv put it in the environment too


def test_a_model_that_cannot_start_is_a_503_not_a_crash(monkeypatch):
    # The real default model with no Groq key: the assistant answers 503, the Discovery endpoints keep working.
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    discovery = make_settings(fake_models=False, groq_api_key="k")
    assistant = Settings(_env_file=None, dev_endpoints=True, auth_disabled=True)
    # No `with`: the startup that would call Groq does not run.
    client = TestClient(create_app(discovery, assistant_settings=assistant))
    assert client.get("/assistant/").status_code == 200
    response = client.post("/v1/dev/chat", json={"persona": "new_student", "message": "hi"})
    assert response.status_code == 503 and "could not start" in response.json()["error"]["message"]
    assert client.get("/healthz").status_code == 200


def test_fake_models_switches_the_assistant_to_fake():
    service = create_app(make_settings(), assistant_settings=Settings(_env_file=None, llm_model="groq:x"))
    assert service.state.assistant_settings.llm_model == "fake"


def test_production_ignores_the_local_testing_switches():
    from app.core.config import Settings as DiscoverySettings

    discovery = DiscoverySettings(_env_file=None, app_env="production", groq_api_key="k", jwt_public_key=PUBLIC)
    assistant = Settings(_env_file=None, auth_public_key_pem=PUBLIC, auth_disabled=True, dev_endpoints=True)
    # No `with`: the startup that would call Groq does not run.
    client = TestClient(create_app(discovery, assistant_settings=assistant))
    assert client.get("/v1/dev/personas").status_code == 404
    assert post(client, body()).status_code == 401


def test_the_default_model_is_groq_gpt_oss_with_low_reasoning(monkeypatch):
    # llama-3.3-70b-versatile was shut down by Groq on 16 Aug 2026.
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.delenv("ASSISTANT_LLM_MODEL", raising=False)
    from assistant.llm import create_model

    settings = Settings(_env_file=None)
    model = create_model(settings)
    assert settings.llm_model == "groq:openai/gpt-oss-120b"
    assert (model.model_name, model.reasoning_effort) == ("openai/gpt-oss-120b", "low")


def test_a_request_without_profile_fields_still_works(client):
    payload = body()
    for field in ("first_name", "gender", "member_since"):
        payload["context"]["student"].pop(field)
    assert post(client, payload, token()).status_code == 200


def test_an_english_question_gets_an_english_demo_reply(dev_client):
    response = dev_client.post("/v1/dev/chat", json={"persona": "frontend_beginner", "message": "how much XP do I have?"})
    assert response.status_code == 200
    data = response.json()
    assert data["reply"].startswith("(demo)") and data["suggestions"] == ["What's my next lesson?"]


def test_dev_chat_profile_question_uses_the_profile_tool(dev_client):
    response = dev_client.post("/v1/dev/chat", json={"persona": "new_student", "message": "اسمي إيه؟"})
    assert response.json()["debug"]["tools"] == ["get_my_profile"]
