"""Idempotent attention-notification delivery.

Attention events (a pending approval, a decision, a wait) are delivered to an actor
at most once per (event, actor): a duplicate event never sends a second message.
Messages are truncated to the transport ceiling. The delivery store is a port; an
in-memory implementation backs tests and the SQLite-backed implementation is wired at
deployment.
"""

from dataclasses import dataclass
from typing import Protocol

MAX_MESSAGE_CHARS = 3500


@dataclass(frozen=True)
class SendResult:
    message_id: str
    status: str


class TelegramTransport(Protocol):
    def send(self, actor_id: str, message: str) -> SendResult: ...


class DeliveryStore(Protocol):
    def delivery_exists(self, event_id: str, actor_id: str) -> bool: ...
    def record_delivery(
        self, event_id: str, actor_id: str, message_id: str, status: str
    ) -> None: ...


class InMemoryDeliveryStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], tuple[str, str]] = {}

    def delivery_exists(self, event_id: str, actor_id: str) -> bool:
        return (event_id, actor_id) in self._records

    def record_delivery(
        self, event_id: str, actor_id: str, message_id: str, status: str
    ) -> None:
        self._records[(event_id, actor_id)] = (message_id, status)


class NotificationService:
    def __init__(self, *, store: DeliveryStore, transport: TelegramTransport) -> None:
        self.store = store
        self.transport = transport

    def deliver(self, event_id: str, actor_id: str, message: str) -> None:
        if self.store.delivery_exists(event_id, actor_id):
            return
        result = self.transport.send(actor_id, message[:MAX_MESSAGE_CHARS])
        self.store.record_delivery(event_id, actor_id, result.message_id, result.status)
