"""Both knowledge receipts must reference the exact canonical commit."""


def test_both_receipts_reference_committed_source(coordinator, completed_evidence) -> None:
    sync = coordinator.preserve(completed_evidence)
    assert sync.qmd_source_commit == sync.canonical_commit
    assert sync.openviking_source_commit == sync.canonical_commit
    assert sync.ready_for_cleanup is True
    assert sync.state == "complete"


def test_preservation_persists_the_sync(coordinator, completed_evidence, store) -> None:
    sync = coordinator.preserve(completed_evidence)
    assert store.saved == [sync]


def test_commit_happens_before_indexing(coordinator, completed_evidence, git, qmd, openviking) -> None:
    coordinator.preserve(completed_evidence)
    assert len(git.commits) == 1
    committed = "commit-1"
    assert qmd.calls[0][1] == committed
    assert openviking.calls[0][2] == committed


def test_openviking_uri_is_recorded_on_success(coordinator, completed_evidence, git) -> None:
    sync = coordinator.preserve(completed_evidence)
    assert sync.openviking_uri == git.source_uri
    assert sync.qmd_collection == completed_evidence.project_id
