"""Liveness / readiness probes (no auth, no provider calls: they must not burn quota)."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness")
async def readyz() -> dict[str, str]:
    return {"status": "ready", "version": __version__}
