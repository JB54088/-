from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import require_admin
from ...models import AgentQueryLog, User
from .planner import AgentQuestionError
from .schemas import AgentQueryRequest, AgentQueryResponse
from .service import rejected_response, run_business_query

router = APIRouter(prefix="/agents/business-analysis", tags=["AI经营助手"])


@router.post("/query", response_model=AgentQueryResponse)
def query_business_analysis(
    payload: AgentQueryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> AgentQueryResponse:
    started = time.perf_counter()
    status = "success"
    try:
        response = run_business_query(db, payload.question)
    except AgentQuestionError as exc:
        status = "rejected"
        response = rejected_response(str(exc))
    except ValueError as exc:
        status = "rejected"
        response = rejected_response(str(exc))
    latency_ms = int((time.perf_counter() - started) * 1000)
    db.add(AgentQueryLog(
        user_id=user.id,
        question=payload.question,
        query_plan_json=response.query_plan.model_dump(mode="json"),
        result_summary=response.answer,
        model_name=response.model_name,
        latency_ms=latency_ms,
        status=status,
    ))
    db.commit()
    return response

