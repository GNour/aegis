"""Scoped, bounded QMD retrieval adapter.

QMD is adopted behind a narrow adapter (docs/rfcs/0005-qmd.md). The binary is not
installed in this environment, so the adapter is validated against an injectable
command runner. A task may only search collections and modes in its scope, the
result limit is bounded, and results are validated: unknown fields, foreign-collection
URIs, and non-list output are rejected, and snippets are byte-truncated. The adapter
owns configuration and never runs a project-supplied collection-update hook.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from aegis.execution.command import CommandResult, run

MAX_SNIPPET_BYTES = 2000
MAX_LIMIT = 20
_ALLOWED_FIELDS = frozenset({"uri", "snippet", "score"})

Runner = Callable[..., CommandResult]


@dataclass(frozen=True)
class RetrievalScope:
    task_id: str
    collections: frozenset[str]
    modes: frozenset[str]


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def validate_results(stdout: str, collection: str, limit: int) -> list[dict[str, object]]:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise ValueError("qmd returned invalid JSON") from error
    if not isinstance(parsed, list):
        raise ValueError("qmd results: expected a JSON list")
    prefix = f"qmd://{collection}/"
    validated: list[dict[str, object]] = []
    for item in parsed[:limit]:
        if not isinstance(item, dict):
            raise ValueError("qmd result item must be an object")
        unknown = set(item) - _ALLOWED_FIELDS
        if unknown:
            raise ValueError(f"qmd result has unknown field(s): {sorted(unknown)}")
        uri = item.get("uri")
        if not isinstance(uri, str) or not uri.startswith(prefix):
            raise ValueError("qmd result references a foreign collection")
        validated.append(
            {
                "uri": uri,
                "snippet": _truncate_utf8(str(item.get("snippet", "")), MAX_SNIPPET_BYTES),
                "score": float(item.get("score", 0.0)),
            }
        )
    return validated


@dataclass
class QmdAdapter:
    runner: Runner = run
    max_limit: int = MAX_LIMIT
    queries: list[dict[str, Any]] = field(default_factory=list)

    def search(
        self,
        scope: RetrievalScope,
        collection: str,
        query: str,
        limit: int = 8,
        mode: str = "lexical",
    ) -> list[dict[str, object]]:
        if collection not in scope.collections:
            raise PermissionError("collection not allowed")
        if mode not in scope.modes:
            raise PermissionError("search mode not allowed")
        if not 1 <= limit <= self.max_limit:
            raise ValueError(f"limit must be between 1 and {self.max_limit}")
        result = self.runner(
            ["qmd", "search", query, "-c", collection, "--json", "-n", str(limit), "--mode", mode],
        )
        results = validate_results(result.stdout, collection, limit)
        self.queries.append(
            {
                "task_id": scope.task_id,
                "collection": collection,
                "mode": mode,
                "uris": [item["uri"] for item in results],
            }
        )
        return results
