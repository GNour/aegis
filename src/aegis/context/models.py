"""Immutable, cited context records."""

from pydantic import BaseModel, ConfigDict, Field


class ContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: str
    content: str
    source_uri: str = Field(min_length=1)
    digest: str
    byte_size: int = Field(ge=0)
    token_estimate: int = Field(ge=0)


class ContextSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    items: tuple[ContextItem, ...]


class ContextEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sections: tuple[ContextSection, ...]
    total_bytes: int = Field(ge=0)
    budget_bytes: int = Field(ge=0)
