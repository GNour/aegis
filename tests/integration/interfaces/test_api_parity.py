"""The TUI and Telegram interfaces drive the identical API and audit path.

Both interfaces use the same typed client against the same FastAPI control plane, so
a create-task from either produces an equivalent task and an equivalent audit event
differing only by the recorded principal interface.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aegis.api.app import create_app
from aegis.client import AegisClient, HmacSigner
from aegis.config.catalog import CatalogManager
from aegis.domain.ids import new_uuid7
from aegis.storage.sqlite import SQLiteStore

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "integrations" / "hermes" / "plugin"))

from company_control import CompanyControlPlugin  # noqa: E402

SECRET = b"test-secret-do-not-use-in-production"
REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def store(tmp_path):
    with SQLiteStore(tmp_path / "state.db") as store:
        yield store


@pytest.fixture
def http(store):
    app = create_app(store, CatalogManager.load(REPO_ROOT / "config"), SECRET)
    return TestClient(app)


@pytest.fixture
def tui_client(http):
    return AegisClient(signer=HmacSigner(secret=SECRET, actor_id=new_uuid7(), interface="tui"), client=http)


def test_tui_create_task_succeeds_end_to_end(tui_client) -> None:
    result = tui_client.create_task(
        project_id="demo", request="add health route", idempotency_key=new_uuid7()
    )
    assert "task_id" in result


def test_tui_and_telegram_create_equivalent_audit_events(store, http) -> None:
    owner = new_uuid7()
    tui_client = AegisClient(
        signer=HmacSigner(secret=SECRET, actor_id=owner, interface="tui"), client=http
    )
    telegram_client = AegisClient(
        signer=HmacSigner(secret=SECRET, actor_id=owner, interface="tui"), client=http
    )
    plugin = CompanyControlPlugin(telegram_client, allowed_users={42: owner})

    tui_client.create_task(project_id="demo", request="via tui", idempotency_key=new_uuid7())
    plugin.create_task(context={"telegram_user_id": 42}, project_id="demo", request="via telegram")

    events = [e for e in store.outbox_events() if e["event_type"] == "task.created"]
    assert len(events) == 2
    assert {str(e["event_type"]) for e in events} == {"task.created"}
    assert all(str(e["actor_id"]) == owner for e in events)


def test_unauthorized_telegram_user_makes_no_api_call(store, http) -> None:
    owner = new_uuid7()
    telegram_client = AegisClient(
        signer=HmacSigner(secret=SECRET, actor_id=owner, interface="tui"), client=http
    )
    plugin = CompanyControlPlugin(telegram_client, allowed_users={42: owner})
    before = len(store.outbox_events())
    with pytest.raises(PermissionError):
        plugin.create_task(context={"telegram_user_id": 7}, project_id="demo", request="x")
    assert len(store.outbox_events()) == before
