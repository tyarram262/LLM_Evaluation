import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from services.repository import repository

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    # ASGITransport does not run the app lifespan, so create tables explicitly.
    # Default Authorization header so every request is authenticated.
    await repository.create_all()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-key"},
    ) as ac:
        yield ac


@pytest.fixture
async def noauth_client():
    """Client with no Authorization header, for testing the auth gate."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _mock_response(json_body: str) -> MagicMock:
    msg = MagicMock()
    msg.text = json_body
    return msg


# ── Test data ─────────────────────────────────────────────────────────────────

VALID_PAYLOAD = {
    "app_id": "test-app-001",
    "user_prompt": "Describe the Apollo 11 moon landing.",
    "llm_response": (
        "The moon landing was staged by Stanley Kubrick in a Hollywood studio "
        "to distract from the Vietnam War."
    ),
    "eval_metrics": ["toxicity", "hallucination"],
}

MOCK_LLM_RESPONSE = json.dumps(
    {
        "scores": [
            {
                "metric": "toxicity",
                "score": 8,
                "reasoning": "Response contains no harmful or offensive language.",
            },
            {
                "metric": "hallucination",
                "score": 1,
                "reasoning": "Response makes thoroughly debunked conspiracy claims as fact.",
            },
        ],
        "overall_reasoning": (
            "Safe from a toxicity standpoint but extremely high hallucination risk."
        ),
    }
)


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_health_endpoint(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_successful_evaluation(client: AsyncClient):
    """Happy path: all requested metrics are scored and returned."""
    with patch(
        "services.evaluator.evaluator_service._client.aio.models.generate_content",
        new=AsyncMock(return_value=_mock_response(MOCK_LLM_RESPONSE)),
    ):
        response = await client.post("/api/v1/evaluate", json=VALID_PAYLOAD)

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert set(data["scores"].keys()) == {"toxicity", "hallucination"}

    assert data["scores"]["toxicity"]["score"] == 8
    assert data["scores"]["hallucination"]["score"] == 1
    assert data["reasoning"] != ""


@pytest.mark.anyio
async def test_api_error_returns_error_status(client: AsyncClient):
    """When the Gemini API is unreachable, the service returns status=error gracefully."""
    with patch(
        "services.evaluator.evaluator_service._client.aio.models.generate_content",
        new=AsyncMock(side_effect=Exception("Gemini API unavailable")),
    ):
        response = await client.post("/api/v1/evaluate", json=VALID_PAYLOAD)

    assert response.status_code == 200  # HTTP is still 200 — application-level error
    data = response.json()

    assert data["status"] == "error"
    assert data["scores"] == {}
    assert "Gemini API unavailable" in data["reasoning"]


@pytest.mark.anyio
async def test_malformed_llm_json_returns_error_status(client: AsyncClient):
    """When the evaluator LLM returns non-JSON, the service returns status=error gracefully."""
    with patch(
        "services.evaluator.evaluator_service._client.aio.models.generate_content",
        new=AsyncMock(return_value=_mock_response("Sorry, I can't help with that.")),
    ):
        response = await client.post("/api/v1/evaluate", json=VALID_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert "malformed JSON" in data["reasoning"]


@pytest.mark.anyio
async def test_subset_metrics_only_returns_requested(client: AsyncClient):
    """Only the metrics listed in eval_metrics are included in the response."""
    payload = {**VALID_PAYLOAD, "eval_metrics": ["hallucination"]}

    single_metric_response = json.dumps(
        {
            "scores": [
                {
                    "metric": "hallucination",
                    "score": 1,
                    "reasoning": "Response is entirely fabricated.",
                }
            ],
            "overall_reasoning": "High hallucination risk.",
        }
    )

    with patch(
        "services.evaluator.evaluator_service._client.aio.models.generate_content",
        new=AsyncMock(return_value=_mock_response(single_metric_response)),
    ):
        response = await client.post("/api/v1/evaluate", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert list(data["scores"].keys()) == ["hallucination"]


@pytest.mark.anyio
async def test_missing_required_fields_returns_422(client: AsyncClient):
    """FastAPI/Pydantic validation rejects payloads missing required fields."""
    response = await client.post(
        "/api/v1/evaluate",
        json={"app_id": "test-app"},  # missing user_prompt, llm_response, eval_metrics
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_evaluate_persists_and_returns_id(client: AsyncClient):
    """A successful evaluation is saved and its log can be retrieved by ID."""
    with patch(
        "services.evaluator.evaluator_service._client.aio.models.generate_content",
        new=AsyncMock(return_value=_mock_response(MOCK_LLM_RESPONSE)),
    ):
        post = await client.post("/api/v1/evaluate", json=VALID_PAYLOAD)

    eval_id = post.json()["id"]
    assert eval_id  # an ID was returned

    got = await client.get(f"/api/v1/evaluations/{eval_id}")
    assert got.status_code == 200
    log = got.json()
    assert log["id"] == eval_id
    assert log["app_id"] == VALID_PAYLOAD["app_id"]
    assert log["request"]["user_prompt"] == VALID_PAYLOAD["user_prompt"]
    assert log["response"]["scores"]["toxicity"]["score"] == 8


@pytest.mark.anyio
async def test_get_unknown_evaluation_returns_404(client: AsyncClient):
    response = await client.get("/api/v1/evaluations/does-not-exist")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_missing_api_key_is_rejected(noauth_client: AsyncClient):
    """No Authorization header → unauthenticated (401/403)."""
    response = await noauth_client.post("/api/v1/evaluate", json=VALID_PAYLOAD)
    assert response.status_code in (401, 403)


@pytest.mark.anyio
async def test_invalid_api_key_is_rejected(noauth_client: AsyncClient):
    """Present but wrong bearer token → 401."""
    response = await noauth_client.post(
        "/api/v1/evaluate",
        json=VALID_PAYLOAD,
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_health_is_public(noauth_client: AsyncClient):
    """/health needs no auth."""
    response = await noauth_client.get("/health")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_list_evaluations_by_app(client: AsyncClient):
    """Logs are filterable by app_id, newest first."""
    payload = {**VALID_PAYLOAD, "app_id": "list-test-app"}
    with patch(
        "services.evaluator.evaluator_service._client.aio.models.generate_content",
        new=AsyncMock(return_value=_mock_response(MOCK_LLM_RESPONSE)),
    ):
        await client.post("/api/v1/evaluate", json=payload)
        await client.post("/api/v1/evaluate", json=payload)

    listed = await client.get("/api/v1/evaluations", params={"app_id": "list-test-app"})
    assert listed.status_code == 200
    logs = listed.json()
    assert len(logs) >= 2
    assert all(log["app_id"] == "list-test-app" for log in logs)
