"""Exceptions raised by providers (kept free of any HTTP framework types)."""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for every provider failure."""


class ProviderAuthError(ProviderError):
    """The API key was rejected. Falling back to another model will not help."""


class ProviderRateLimited(ProviderError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderTimeout(ProviderError):
    """The provider did not answer in time."""


class ProviderServerError(ProviderError):
    """5xx or a network failure."""


class ProviderRejected(ProviderError):
    """The provider refused the request (400/413/422, e.g. too many tokens)."""


class ProviderBadOutput(ProviderError):
    """The provider answered, but with unusable content."""


class ProviderExhausted(ProviderError):
    """Every configured model failed."""
