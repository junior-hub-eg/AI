"""Service-to-service authentication (RS256 JWT issued by the backend)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings
from app.core.errors import Unauthenticated
from app.core.logging import log_event

logger = logging.getLogger(__name__)


class Authenticator(Protocol):
    def verify(self, token: str | None) -> None:
        """Return normally if the token is valid, raise Unauthenticated otherwise."""


class JwtAuthenticator:
    def __init__(
        self, *, public_key_pem: str, audience: str, issuer: str | None, leeway_seconds: int
    ) -> None:
        key = serialization.load_pem_public_key(public_key_pem.encode())
        if not isinstance(key, rsa.RSAPublicKey):
            raise ValueError("JWT public key must be an RSA key (RS256)")
        self._key = key
        self._audience = audience
        self._issuer = issuer
        self._leeway = leeway_seconds

    def verify(self, token: str | None) -> None:
        if not token:
            raise Unauthenticated()
        try:
            jwt.decode(
                token,
                self._key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "aud"]},
            )
        except jwt.PyJWTError as exc:
            log_event(logger, logging.WARNING, "auth_rejected", reason=type(exc).__name__)
            raise Unauthenticated() from None


class DisabledAuthenticator:
    """Accepts every request. Development only (refused in production)."""

    def verify(self, token: str | None) -> None:
        return None


def build_authenticator(settings: Settings) -> Authenticator:
    if settings.auth_disabled:
        logger.warning("AUTH IS DISABLED - never do this outside local development")
        return DisabledAuthenticator()
    if settings.jwt_public_key_file:
        pem = Path(settings.jwt_public_key_file).read_text(encoding="utf-8")
    else:
        pem = (settings.jwt_public_key or "").replace("\\n", "\n")
    return JwtAuthenticator(
        public_key_pem=pem,
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        leeway_seconds=settings.jwt_leeway_seconds,
    )
