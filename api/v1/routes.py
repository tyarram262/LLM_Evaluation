from fastapi import APIRouter, HTTPException, Query, Request

from config import settings
from models.schemas import EvalRequest, EvalResponse, EvaluationLog
from rate_limit import limiter
from services.evaluator import evaluator_service
from services.repository import repository

router = APIRouter()


@router.post("/evaluate", response_model=EvalResponse, summary="Evaluate an LLM response")
@limiter.limit(settings.rate_limit)
async def evaluate(request: Request, payload: EvalRequest) -> EvalResponse:
    """
    Submit an LLM prompt+response pair for automated grading.

    Returns a 1–10 score per requested metric plus a one-sentence reasoning summary.
    Every evaluation is persisted; the returned `id` can be used to retrieve it later.

    `request: Request` is required by the rate limiter; `payload` is the JSON body.
    """
    response = await evaluator_service.evaluate(payload)
    record_id = await repository.save(
        app_id=payload.app_id,
        request=payload.model_dump(),
        # The log carries its own top-level id; drop the redundant nested one.
        response=response.model_dump(exclude={"id"}),
    )
    response.id = record_id
    return response


@router.get(
    "/evaluations/{evaluation_id}",
    response_model=EvaluationLog,
    summary="Retrieve a single evaluation by ID",
)
async def get_evaluation(evaluation_id: str) -> EvaluationLog:
    record = await repository.find_by_id(evaluation_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Evaluation '{evaluation_id}' not found")
    return record


@router.get(
    "/evaluations",
    response_model=list[EvaluationLog],
    summary="List evaluations for an app (most recent first)",
)
async def list_evaluations(
    app_id: str = Query(..., description="Filter logs to this application"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
) -> list[EvaluationLog]:
    return await repository.find_by_app(app_id, limit=limit)
