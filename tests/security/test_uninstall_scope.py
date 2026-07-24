"""Uninstall preserves data by default and never touches unrelated resources."""

import pytest

from aegis.deploy.runtime import FakeContainerRuntime
from aegis.deploy.uninstall import uninstall


def _runtime() -> FakeContainerRuntime:
    runtime = FakeContainerRuntime()
    runtime.seed("aegis", ["aegis-control"])
    return runtime


def test_uninstall_preserves_data_by_default(tmp_path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "state.db").write_text("keep", encoding="utf-8")
    runtime = _runtime()

    result = uninstall(runtime, "aegis", data_paths=[data], allowed_roots=[tmp_path])
    assert runtime.exists("aegis") is False
    assert data.exists()
    assert result.purged_paths == []
    assert all("prune" not in " ".join(cmd) for cmd in runtime.commands)


def test_purge_requires_confirmation(tmp_path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    with pytest.raises(ValueError, match="confirmation"):
        uninstall(
            _runtime(), "aegis", data_paths=[data], allowed_roots=[tmp_path], purge_data=True
        )


def test_purge_with_confirmation_removes_validated_paths(tmp_path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "state.db").write_text("gone", encoding="utf-8")
    result = uninstall(
        _runtime(),
        "aegis",
        data_paths=[data],
        allowed_roots=[tmp_path],
        purge_data=True,
        confirm=True,
    )
    assert not data.exists()
    assert str(data) in [str(p) for p in result.purged_paths]


def test_purge_rejects_path_outside_allowed_roots(tmp_path) -> None:
    outside = tmp_path.parent / "somewhere-else"
    with pytest.raises(ValueError, match="outside"):
        uninstall(
            _runtime(),
            "aegis",
            data_paths=[outside],
            allowed_roots=[tmp_path],
            purge_data=True,
            confirm=True,
        )
