"""RTK compression feeds the model; the full stream is always retained as an artifact."""

import pytest

from aegis.execution.output import FilesystemArtifactStore, OutputCapture


@pytest.fixture
def capture(tmp_path) -> OutputCapture:
    return OutputCapture(FilesystemArtifactStore(tmp_path / "artifacts"))


def test_model_receives_compressed_output_and_artifact_keeps_full_text(capture, tmp_path) -> None:
    result = capture.record(command_id="c1", full="100 passed\n" * 100, compressed="100 passed")
    assert result.model_text == "100 passed"
    assert result.full_artifact.read_text() == "100 passed\n" * 100
    assert result.saved_bytes > 0


def test_full_artifact_is_owner_only(capture) -> None:
    result = capture.record(command_id="c2", full="x" * 10, compressed="x")
    assert result.full_artifact.stat().st_mode & 0o077 == 0


def test_no_savings_when_output_is_not_compressed(capture) -> None:
    result = capture.record(command_id="c3", full="same", compressed="same")
    assert result.saved_bytes == 0
    assert result.full_bytes == result.model_bytes


def test_rtk_version_is_recorded(capture) -> None:
    result = capture.record(command_id="c4", full="a\nb\n", compressed="a", rtk_version="1.4.2")
    assert result.rtk_version == "1.4.2"


def test_artifact_path_traversal_is_rejected(capture) -> None:
    with pytest.raises(ValueError, match="escapes"):
        capture.record(command_id="../../evil", full="x", compressed="x")
