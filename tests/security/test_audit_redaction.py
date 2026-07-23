from aegis.audit.ledger import Ledger


def test_secret_and_raw_request_are_redacted_before_hashing(tmp_path) -> None:
    ledger = Ledger(tmp_path / "audit.jsonl")
    secret = "sk-" + "proj-abcdefghijk"
    request = f"password=hunter2 authorization=Bearer top-secret {secret} /home/agent/.ssh/id_ed25519"

    ledger.append("task.created", {"request": request, "api_key": "never-store-me"})

    text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    for value in ("hunter2", "top-secret", secret, "id_ed25519", "never-store-me"):
        assert value not in text
    assert ledger.verify() == []
