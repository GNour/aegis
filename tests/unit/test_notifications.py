"""Attention notifications are delivered at most once per event/actor and bounded."""

import pytest

from aegis.notifications import (
    MAX_MESSAGE_CHARS,
    InMemoryDeliveryStore,
    NotificationService,
    SendResult,
)


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self._counter = 0

    def send(self, actor_id: str, message: str) -> SendResult:
        self._counter += 1
        self.messages.append((actor_id, message))
        return SendResult(message_id=f"m{self._counter}", status="sent")


@pytest.fixture
def telegram() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def notifier(telegram: FakeTelegram) -> NotificationService:
    return NotificationService(store=InMemoryDeliveryStore(), transport=telegram)


def test_duplicate_attention_event_delivers_once(notifier, telegram) -> None:
    notifier.deliver(event_id="e1", actor_id="owner", message="Approval A1 needs review")
    notifier.deliver(event_id="e1", actor_id="owner", message="Approval A1 needs review")
    assert len(telegram.messages) == 1


def test_distinct_events_each_deliver(notifier, telegram) -> None:
    notifier.deliver(event_id="e1", actor_id="owner", message="A")
    notifier.deliver(event_id="e2", actor_id="owner", message="B")
    assert len(telegram.messages) == 2


def test_same_event_different_actor_both_deliver(notifier, telegram) -> None:
    notifier.deliver(event_id="e1", actor_id="owner", message="A")
    notifier.deliver(event_id="e1", actor_id="deputy", message="A")
    assert len(telegram.messages) == 2


def test_message_is_truncated_to_ceiling(notifier, telegram) -> None:
    notifier.deliver(event_id="e1", actor_id="owner", message="x" * 10000)
    assert len(telegram.messages[0][1]) == MAX_MESSAGE_CHARS


def test_delivery_is_recorded(telegram) -> None:
    store = InMemoryDeliveryStore()
    NotificationService(store=store, transport=telegram).deliver(
        event_id="e1", actor_id="owner", message="A"
    )
    assert store.delivery_exists("e1", "owner") is True
