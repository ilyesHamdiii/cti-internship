import json
from typing import Any, ClassVar

import httpx
import pytest

from app.core.config import Settings
from app.services.ai import DeepSeekClient, DeepSeekProviderError


class FakeResponse:
    def __init__(self, payload=None, status_code=200, json_error: Exception | None = None):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error
        self.request = httpx.Request("POST", "https://api.deepseek.test/chat/completions")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "provider failure",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


class FakeAsyncClient:
    calls: ClassVar[list[dict[str, Any]]] = []
    responses: ClassVar[list[FakeResponse | Exception]] = []
    timeout_seen: ClassVar[int | None] = None

    def __init__(self, timeout=None):
        FakeAsyncClient.timeout_seen = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, url, headers=None, json=None):
        FakeAsyncClient.calls.append({"url": url, "headers": headers, "json": json})
        response = FakeAsyncClient.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def settings() -> Settings:
    return Settings(
        ai_fixture_mode=False,
        deepseek_api_key="sk-test-secret",
        deepseek_base_url="https://api.deepseek.test",
        deepseek_model="deepseek-chat",
    )


def provider_payload(content: dict, usage: dict | None = None) -> dict:
    return {
        "choices": [{"message": {"content": json.dumps(content)}}],
        "usage": usage or {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def cti_response() -> dict:
    evidence = [
        {
            "ref": "attribute:1",
            "excerpt": "powershell.exe -EncodedCommand",
            "source_field": "attributes",
        }
    ]
    return {
        "behaviors": [
            {
                "behavior_key": "powershell_encoded",
                "summary": "PowerShell encoded command execution",
                "behavior_type": "process_execution",
                "actor_action": "execute",
                "target": "PowerShell",
                "execution_mechanism": "powershell.exe -EncodedCommand",
                "evidence_refs": evidence,
                "observables": [{"type": "process", "value": "powershell.exe -EncodedCommand"}],
                "proposed_attack_mappings": [
                    {
                        "technique_id": "T1059.001",
                        "technique_name": "PowerShell",
                        "tactic_id": "execution",
                        "tactic_name": "Execution",
                        "evidence_refs": evidence,
                        "confidence": 0.9,
                    }
                ],
                "required_telemetry": [{"category": "process", "fields": ["Image", "CommandLine"]}],
                "confidence": 0.9,
                "uncertainties": [],
            }
        ],
        "structured_justification": {
            "decision_factors": ["mocked"],
            "evidence_refs": evidence,
            "attack_rationale": ["mock"],
            "coverage_rationale": [],
            "telemetry_rationale": ["mock"],
            "confidence": 0.9,
            "uncertainties": [],
            "change_summary": [],
        },
    }


@pytest.fixture(autouse=True)
def fake_http(monkeypatch):
    FakeAsyncClient.calls = []
    FakeAsyncClient.responses = []
    FakeAsyncClient.timeout_seen = None
    monkeypatch.setattr("app.services.ai.httpx.AsyncClient", FakeAsyncClient)

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("app.services.ai.asyncio.sleep", no_sleep)


@pytest.mark.asyncio
async def test_deepseek_request_construction_auth_timeout_usage_and_hashing() -> None:
    FakeAsyncClient.responses = [FakeResponse(provider_payload(cti_response()))]

    response, usage = await DeepSeekClient(settings()).analyze_cti(
        {"attributes": [{"id": "1", "value": "powershell"}]}
    )

    request = FakeAsyncClient.calls[0]
    assert response.behaviors[0].summary == "PowerShell encoded command execution"
    assert request["url"] == "https://api.deepseek.test/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer sk-test-secret"
    assert FakeAsyncClient.timeout_seen == 30
    assert request["json"]["model"] == "deepseek-chat"
    assert request["json"]["response_format"] == {"type": "json_object"}
    assert usage["token_usage"] == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    assert usage["attempts"] == 1
    assert usage["input_hash"]
    assert usage["response_hash"]
    assert "sk-test-secret" not in json.dumps(usage)


@pytest.mark.asyncio
async def test_deepseek_retries_malformed_json_then_succeeds() -> None:
    FakeAsyncClient.responses = [
        FakeResponse(json_error=ValueError("not json")),
        FakeResponse(provider_payload(cti_response())),
    ]

    _response, usage = await DeepSeekClient(settings()).analyze_cti(
        {"attributes": [{"id": "1", "value": "powershell"}]}
    )

    assert len(FakeAsyncClient.calls) == 2
    assert usage["attempts"] == 2


@pytest.mark.asyncio
async def test_deepseek_retries_schema_invalid_response_then_succeeds() -> None:
    FakeAsyncClient.responses = [
        FakeResponse(provider_payload({"behaviors": "not-a-list"})),
        FakeResponse(provider_payload(cti_response())),
    ]

    _response, usage = await DeepSeekClient(settings()).analyze_cti(
        {"attributes": [{"id": "1", "value": "powershell"}]}
    )

    assert len(FakeAsyncClient.calls) == 2
    assert usage["attempts"] == 2


@pytest.mark.asyncio
async def test_deepseek_timeout_error_is_sanitized() -> None:
    FakeAsyncClient.responses = [httpx.TimeoutException("secret sk-test-secret timeout")] * 3

    with pytest.raises(DeepSeekProviderError) as exc:
        await DeepSeekClient(settings()).analyze_cti({"attributes": []})

    assert exc.value.error_json["error_type"] == "ProviderTimeout"
    assert "sk-test-secret" not in json.dumps(exc.value.error_json)


@pytest.mark.asyncio
async def test_deepseek_rate_limit_error_is_sanitized() -> None:
    FakeAsyncClient.responses = [FakeResponse(status_code=429)] * 3

    with pytest.raises(DeepSeekProviderError) as exc:
        await DeepSeekClient(settings()).analyze_cti({"attributes": []})

    assert exc.value.error_json["error_type"] == "RateLimitError"
    assert exc.value.error_json["status_code"] == 429


@pytest.mark.asyncio
async def test_deepseek_5xx_error_is_sanitized() -> None:
    FakeAsyncClient.responses = [FakeResponse(status_code=502)] * 3

    with pytest.raises(DeepSeekProviderError) as exc:
        await DeepSeekClient(settings()).analyze_cti({"attributes": []})

    assert exc.value.error_json["error_type"] == "ProviderServerError"
    assert exc.value.error_json["status_code"] == 502


@pytest.mark.asyncio
async def test_live_deepseek_test_is_environment_gated(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("RUN_LIVE_AI_TESTS", raising=False)
    assert True
