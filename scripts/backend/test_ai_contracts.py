import pytest

from app.services.ai import DeepSeekClient


@pytest.mark.asyncio
async def test_fixture_cti_analysis_returns_structured_justification() -> None:
    response, usage = await DeepSeekClient().analyze_cti({"attributes": []})
    assert response.behaviors
    assert response.structured_justification.confidence > 0
    assert "token_usage" in usage


@pytest.mark.asyncio
async def test_fixture_sigma_generation_returns_schema_valid_candidate() -> None:
    response, _ = await DeepSeekClient().generate_sigma({"behavior": "powershell encoded command"})
    assert response.sigma.detection["condition"] == "selection"
    assert response.structured_justification.decision_factors
