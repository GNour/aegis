"""Bounded, ordered, deduplicated context compilation.

The compiler selects context in a fixed priority order, keeps only items that fit
the remaining byte budget (and an optional per-source ceiling), and deduplicates by
digest so the same fact is never sent twice. Raw transcripts are never a default
source: only curated, cited records enter the envelope.
"""

from collections.abc import Callable, Mapping

from aegis.context.models import ContextEnvelope, ContextItem, ContextSection

Source = Callable[[object], list[ContextItem]]


class ContextCompiler:
    ORDER: tuple[str, ...] = (
        "stage_contract",
        "acceptance",
        "decisions",
        "handoff",
        "skills",
        "files",
        "qmd",
        "openviking",
    )

    def __init__(self, sources: Mapping[str, Source]) -> None:
        self.sources = sources

    def compile(
        self,
        request: object,
        max_bytes: int,
        max_section_bytes: int | None = None,
    ) -> ContextEnvelope:
        seen: set[str] = set()
        remaining = max_bytes
        sections: list[ContextSection] = []
        for name in self.ORDER:
            source = self.sources.get(name)
            if source is None:
                continue
            section_remaining = max_section_bytes if max_section_bytes is not None else remaining
            kept: list[ContextItem] = []
            for item in source(request):
                if item.digest in seen:
                    continue
                if item.byte_size > remaining or item.byte_size > section_remaining:
                    continue
                kept.append(item)
                seen.add(item.digest)
                remaining -= item.byte_size
                section_remaining -= item.byte_size
            if kept:
                sections.append(ContextSection(name=name, items=tuple(kept)))
        return ContextEnvelope(
            sections=tuple(sections),
            total_bytes=max_bytes - remaining,
            budget_bytes=max_bytes,
        )
