"""The context compiler produces a bounded, ordered, deduplicated, cited envelope."""

import pytest

from aegis.context.compiler import ContextCompiler
from aegis.context.models import ContextItem


def _item(kind: str, content: str, digest: str, uri: str = "git://brain/x.md") -> ContextItem:
    body = content.encode("utf-8")
    return ContextItem(
        kind=kind,
        content=content,
        source_uri=uri,
        digest=digest,
        byte_size=len(body),
        token_estimate=max(1, len(body) // 4),
    )


@pytest.fixture
def ctx_request() -> dict[str, str]:
    return {"task_id": "t1"}


@pytest.fixture
def compiler() -> ContextCompiler:
    shared = _item("decision", "shared decision", "d-shared")
    sources = {
        "stage_contract": lambda r: [_item("contract", "the contract", "d-contract")],
        "acceptance": lambda r: [_item("acceptance", "criteria", "d-accept")],
        "decisions": lambda r: [shared],
        "handoff": lambda r: [shared],  # duplicate digest -> deduped away
        "skills": lambda r: [_item("skill", "skill body", "d-skill")],
        "files": lambda r: [_item("file", "F" * 5000, "d-bigfile")],  # oversized -> skipped
        "qmd": lambda r: [_item("qmd", "snippet", "d-qmd")],
        "openviking": lambda r: [_item("openviking", "memory", "d-ov")],
    }
    return ContextCompiler(sources)


def test_context_is_bounded_and_deduplicated(compiler, ctx_request) -> None:
    envelope = compiler.compile(ctx_request, max_bytes=4096)
    assert envelope.total_bytes <= 4096
    digests = [item.digest for section in envelope.sections for item in section.items]
    assert len(digests) == len(set(digests))
    assert envelope.sections[0].name == "stage_contract"


def test_full_transcript_is_not_a_default_source(compiler, ctx_request) -> None:
    envelope = compiler.compile(ctx_request, max_bytes=4096)
    assert all(
        item.kind != "raw_transcript"
        for section in envelope.sections
        for item in section.items
    )


def test_oversized_item_is_skipped(compiler, ctx_request) -> None:
    envelope = compiler.compile(ctx_request, max_bytes=4096)
    assert "files" not in {section.name for section in envelope.sections}


def test_sections_follow_declared_order(compiler, ctx_request) -> None:
    envelope = compiler.compile(ctx_request, max_bytes=4096)
    names = [section.name for section in envelope.sections]
    order = list(ContextCompiler.ORDER)
    positions = [order.index(name) for name in names]
    assert positions == sorted(positions)


def test_every_item_is_cited(compiler, ctx_request) -> None:
    envelope = compiler.compile(ctx_request, max_bytes=4096)
    assert all(
        item.source_uri for section in envelope.sections for item in section.items
    )


def test_empty_sources_yield_empty_envelope(ctx_request) -> None:
    envelope = ContextCompiler({}).compile(ctx_request, max_bytes=4096)
    assert envelope.sections == ()
    assert envelope.total_bytes == 0


def test_per_source_ceiling_is_enforced() -> None:
    sources = {
        "stage_contract": lambda r: [
            _item("contract", "a" * 100, "d1"),
            _item("contract", "b" * 100, "d2"),
        ]
    }
    envelope = ContextCompiler(sources).compile({}, max_bytes=4096, max_section_bytes=100)
    assert sum(len(section.items) for section in envelope.sections) == 1


def test_envelope_is_frozen(compiler, ctx_request) -> None:
    envelope = compiler.compile(ctx_request, max_bytes=4096)
    with pytest.raises(Exception):
        envelope.total_bytes = 0  # type: ignore[misc]
