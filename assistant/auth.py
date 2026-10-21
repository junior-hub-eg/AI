"""Checks the backend's service token: RS256, audience assistant-ai, issuer JuniorHub.Api, at most 5 minutes old."""

from __future__ import annotations

import jwt
from fastapi import Request

from .config import Settings


class Unauthenticated(Exception):
    pass


def verify(request: Request, settings: Settings) -> None:
    if settings.auth_disabled:
        return
    key = settings.public_key()
    if not key:
        raise Unauthenticated("The service has no public key configured.")

    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthenticated("Missing bearer token.")
    try:
        jwt.decode(
            token, key, algorithms=["RS256"], audience=settings.auth_audience, issuer=settings.auth_issuer,
            leeway=30, options={"require": ["exp", "iat", "nbf", "aud", "iss"]},
        )
    except jwt.PyJWTError as error:
        raise Unauthenticated(type(error).__name__) from error
