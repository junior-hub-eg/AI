"""FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, Request

from app.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


async def authenticate(request: Request, container: Container = Depends(get_container)) -> None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    container.auth.verify(token.strip() if scheme.lower() == "bearer" else None)
