"""UUIDv7 identifiers and UTC timestamp helpers for domain records."""

from datetime import UTC, datetime
from secrets import randbits
from typing import Annotated
from uuid import RFC_4122, UUID

from pydantic import AfterValidator, PlainSerializer


def new_uuid7() -> str:
    """Create a canonical RFC 4122 UUIDv7 without an external dependency."""
    timestamp_ms = int(datetime.now(UTC).timestamp() * 1_000)
    value = (
        (timestamp_ms << 80)
        | (0x7 << 76)
        | (randbits(12) << 64)
        | (0b10 << 62)
        | randbits(62)
    )
    return str(UUID(int=value))


def ensure_uuid7(value: str) -> str:
    """Validate and normalize a canonical UUIDv7 string."""
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("value must be a canonical UUIDv7 string") from error
    if str(parsed) != value or parsed.version != 7 or parsed.variant != RFC_4122:
        raise ValueError("value must be a canonical UUIDv7 string")
    return value


def ensure_utc(value: datetime) -> datetime:
    """Reject datetimes that are naive or not explicitly UTC."""
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError("timestamp must be timezone-aware UTC")
    return value.astimezone(UTC)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def _serialize_utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


UUID7 = Annotated[str, AfterValidator(ensure_uuid7)]
UtcDatetime = Annotated[
    datetime,
    AfterValidator(ensure_utc),
    PlainSerializer(_serialize_utc, return_type=str, when_used="json"),
]
