"""Discovery interview endpoints (called by the backend only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import authenticate, get_container
from app.container import Container
from app.schemas.result import ResultRequest, ResultResponse
from app.schemas.turn import TurnRequest, TurnResponse

router = APIRouter(prefix="/v1/discovery", tags=["discovery"], dependencies=[Depends(authenticate)])


@router.post("/turns", response_model=TurnResponse, summary="Answer in, next question out")
async def post_turn(body: TurnRequest, container: Container = Depends(get_container)) -> TurnResponse:
    return await container.turn_service.run(body)


@router.post("/results", response_model=ResultResponse, summary="Top 3 recommended tracks")
async def post_result(body: ResultRequest, container: Container = Depends(get_container)) -> ResultResponse:
    return await container.result_service.run(body)
