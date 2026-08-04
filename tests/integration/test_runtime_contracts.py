from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import pytest


BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8080").rstrip("/")
ADMIN_EMAIL = os.getenv("E2E_ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("E2E_ADMIN_PASSWORD", "ChangeMe123!")


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="runtime integration tests require RUN_INTEGRATION_TESTS=1 and a running Docker stack",
)


def request_json(path: str, *, method: str = "GET", token: str | None = None, body: dict | None = None) -> dict:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1{path}",
        data=payload,
        method=method,
        headers={
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


@pytest.fixture(scope="session")
def token() -> str:
    payload = request_json(
        "/auth/login",
        method="POST",
        body={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    return payload["access_token"]


def wait_for_items(path: str, token: str, minimum: int = 1, timeout: int = 120) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        last = request_json(path, token=token)
        if int(last.get("total", 0)) >= minimum or len(last.get("items", [])) >= minimum:
            return last
        time.sleep(5)
    return last


def test_fastapi_postgres_redis_and_health(token: str) -> None:
    health = request_json("/health")
    assert health["status"] == "ok"

    dashboard = request_json("/dashboard/summary", token=token)
    assert {"pending_cti", "running_workflows", "proposal_count", "detection_count"} <= set(dashboard)

    system_health = request_json("/system-health", token=token)
    components = {item.get("component") for item in system_health["items"]}
    assert {"postgresql", "redis", "misp_api", "pysigma"} <= components


def test_misp_ingestion_normalization_langgraph_and_ai_fixture(token: str) -> None:
    misp_events = wait_for_items("/misp/events?limit=10", token)
    assert misp_events["items"], "MISP API listing should return the scenario event"

    cti_events = wait_for_items("/cti-events?limit=10", token)
    assert cti_events["items"], "MISP polling should normalize at least one CTI event"

    graph_runs = wait_for_items("/graph-runs?limit=10", token)
    assert graph_runs["items"], "normalized CTI should create a LangGraph run"

    ai_workflow = request_json("/ai/workflow", token=token)
    node_names = {node.get("node") for node in ai_workflow.get("nodes", [])}
    assert {"consume_cti", "extract_behaviors", "validate_candidate"} <= node_names

    ai_dashboard = request_json("/ai/dashboard", token=token)
    assert "provider" in ai_dashboard


def test_watchers_trust_session_memory_proposals_review_and_catalog(token: str) -> None:
    sessions = wait_for_items("/ai/sessions?limit=10", token)
    assert sessions["items"], "AI reasoning sessions should be persisted"

    session_id = sessions["items"][0]["id"]
    session = request_json(f"/ai/sessions/{session_id}", token=token)
    assert "revisions" in session
    assert "watchers" in session

    proposals = wait_for_items("/proposals?limit=10", token)
    if not proposals["items"]:
        pytest.skip("scenario routed terminally before proposal creation")

    proposal_id = proposals["items"][0]["id"]
    secondary_proposal_id = proposals["items"][1]["id"] if len(proposals["items"]) > 1 else None
    workspace = request_json(f"/proposals/{proposal_id}/workspace", token=token)
    assert "proposal" in workspace
    assert "current_revision" in workspace
    assert "validation" in workspace

    revisions = request_json(f"/proposals/{proposal_id}/revisions", token=token)
    assert revisions["items"]

    if secondary_proposal_id:
        request_json(
            f"/proposals/{secondary_proposal_id}/request-changes",
            method="POST",
            token=token,
            body={"comment": "CI request changes smoke test"},
        )
    approved = request_json(
        f"/proposals/{proposal_id}/approve",
        method="POST",
        token=token,
        body={"comment": "CI approval smoke test"},
    )
    assert approved["status"] in {"approved", "deployed"}

    detections = wait_for_items("/detections?limit=10", token)
    assert detections["items"], "approval should publish a detection catalog entry"


def test_unauthorized_api_is_blocked() -> None:
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        request_json("/dashboard/summary")
    assert excinfo.value.code in {401, 403}
