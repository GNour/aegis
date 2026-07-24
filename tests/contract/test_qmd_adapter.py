"""Contract tests for the QMD retrieval adapter against recorded CLI output."""

import json

import pytest

from aegis.execution.command import CommandResult
from aegis.knowledge.qmd import MAX_SNIPPET_BYTES, QmdAdapter, RetrievalScope


class RecordingRunner:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv, **kwargs) -> CommandResult:
        self.calls.append(tuple(argv))
        return CommandResult(argv=tuple(argv), returncode=0, stdout=self.stdout, stderr="")


def _scope() -> RetrievalScope:
    return RetrievalScope(
        task_id="t1", collections=frozenset({"project-a"}), modes=frozenset({"lexical"})
    )


def _adapter(stdout: str) -> tuple[QmdAdapter, RecordingRunner]:
    runner = RecordingRunner(stdout)
    return QmdAdapter(runner=runner), runner


def test_authorized_search_returns_cited_results() -> None:
    stdout = json.dumps(
        [{"uri": "qmd://project-a/routes.md#1", "snippet": "def route()", "score": 0.9}]
    )
    adapter, runner = _adapter(stdout)
    results = adapter.search(_scope(), collection="project-a", query="routes", limit=5)
    assert results[0]["uri"].startswith("qmd://project-a/")
    argv = runner.calls[0]
    assert argv[0] == "qmd" and "search" in argv and "--json" in argv
    assert "-c" in argv and "project-a" in argv


def test_foreign_collection_uri_is_rejected() -> None:
    stdout = json.dumps([{"uri": "qmd://project-b/secret.md#1", "snippet": "x", "score": 0.1}])
    adapter, _ = _adapter(stdout)
    with pytest.raises(ValueError, match="foreign collection"):
        adapter.search(_scope(), collection="project-a", query="x", limit=5)


def test_unknown_field_is_rejected() -> None:
    stdout = json.dumps(
        [{"uri": "qmd://project-a/a#1", "snippet": "x", "score": 0.1, "evil": "y"}]
    )
    adapter, _ = _adapter(stdout)
    with pytest.raises(ValueError, match="unknown field"):
        adapter.search(_scope(), collection="project-a", query="x", limit=5)


def test_snippet_bytes_are_truncated() -> None:
    stdout = json.dumps([{"uri": "qmd://project-a/a#1", "snippet": "z" * 10000, "score": 0.1}])
    adapter, _ = _adapter(stdout)
    results = adapter.search(_scope(), collection="project-a", query="x", limit=5)
    assert len(results[0]["snippet"].encode("utf-8")) <= MAX_SNIPPET_BYTES


def test_results_are_capped_to_limit() -> None:
    stdout = json.dumps(
        [{"uri": f"qmd://project-a/a#{i}", "snippet": "s", "score": 0.1} for i in range(10)]
    )
    adapter, _ = _adapter(stdout)
    results = adapter.search(_scope(), collection="project-a", query="x", limit=3)
    assert len(results) <= 3


def test_non_list_output_is_rejected() -> None:
    adapter, _ = _adapter('{"not": "a list"}')
    with pytest.raises(ValueError, match="expected a JSON list"):
        adapter.search(_scope(), collection="project-a", query="x", limit=5)
