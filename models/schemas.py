from typing import Literal
from pydantic import BaseModel, Field


class EvalRequest(BaseModel):
    app_id: str = Field(..., description="Identifier for the application being evaluated")
    user_prompt: str = Field(..., description="The original prompt sent to the LLM")
    llm_response: str = Field(..., description="The LLM response to evaluate")
    eval_metrics: list[str] = Field(
        ...,
        description="Metrics to evaluate e.g. ['toxicity', 'hallucination', 'brand_safety']",
        min_length=1,
    )


class MetricScore(BaseModel):
    score: int = Field(..., ge=1, le=10, description="Score 1 (worst/riskiest) to 10 (best/safest)")
    reasoning: str = Field(..., description="One-sentence explanation of this score")


class EvalResponse(BaseModel):
    id: str | None = Field(default=None, description="ID of the stored evaluation log")
    status: Literal["success", "error"]
    scores: dict[str, MetricScore] = Field(default_factory=dict)
    reasoning: str = Field(..., description="Overall summary or error message")


class EvaluationLog(BaseModel):
    """A persisted evaluation record returned by the retrieval endpoints."""

    id: str
    app_id: str
    timestamp: str
    request: EvalRequest
    response: EvalResponse
