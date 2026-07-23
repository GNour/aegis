"""Conservative redaction applied before audit data is persisted or hashed."""

import re
from collections.abc import Mapping
from typing import Final

REDACTED: Final = "[REDACTED]"
_SENSITIVE_KEYS: Final = frozenset(
    {
        "api-key",
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "credentials",
        "password",
        "request",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "private_key",
    }
)
_KEY_VALUE: Final = re.compile(
    r"\b(?P<key>api[_-]?key|authorization|credential|password|secret|token)\s*[:=]\s*(?P<value>[^\s,;]+)",
    re.IGNORECASE,
)
_BEARER: Final = re.compile(r"\bbearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE)
_TOKEN: Final = re.compile(
    r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9_-]{8,}|github_pat_[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b",
    re.IGNORECASE,
)
_CREDENTIAL_PATH: Final = re.compile(
    r"(?<!\w)(?:~|/)(?:[A-Za-z0-9_.-]+/)*(?:\.ssh|\.aws|secrets?|credentials?|keys?)(?:/[A-Za-z0-9_.-]+)*",
    re.IGNORECASE,
)


def redact(value: object) -> object:
    """Return a recursively redacted copy suitable for durable audit persistence."""
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if str(key).lower() in _SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(value: str) -> str:
    value = _KEY_VALUE.sub(lambda match: f"{match.group('key')}={REDACTED}", value)
    value = _BEARER.sub(f"Bearer {REDACTED}", value)
    value = _TOKEN.sub(REDACTED, value)
    return _CREDENTIAL_PATH.sub(REDACTED, value)
