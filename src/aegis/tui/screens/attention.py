"""Attention screen: render decisions and one-use approvals for the operator.

An approval shows the exact action digest, scope, risk, expiry, and effect so the
operator authorizes precisely the action Aegis computed. Approving forwards the exact
action payload (whose digest must match) through the typed client; rejecting forwards
a reason. The screen never constructs the action itself.
"""

from typing import Any

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static

from aegis.client import AegisClientError
from aegis.domain.ids import new_uuid7


class AttentionScreen(Screen[None]):
    def __init__(self, client: Any, request: Any) -> None:
        super().__init__()
        self.client = client
        self.request = request

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            kind = getattr(self.request, "kind", "approval")
            if kind == "decision":
                yield Static(f"question: {getattr(self.request, 'question', '')}", id="question")
                yield Static(
                    "options: " + ", ".join(getattr(self.request, "options", [])), id="options"
                )
                yield Static(
                    "evidence: " + "; ".join(getattr(self.request, "evidence", [])), id="evidence"
                )
            else:
                yield Static(f"digest: {self.request.action_digest}", id="action-digest")
                yield Static(f"scope: {self.request.scope}", id="scope")
                yield Static(f"risk: {self.request.risk}", id="risk")
                yield Static(f"expires: {self.request.expires_at}", id="expires")
                yield Static(f"effect: {getattr(self.request, 'effect', '')}", id="effect")
            yield Input(placeholder="reason (for reject)", id="reason")
            yield Static("", id="attention-status")
            yield Button("Approve", id="approve", variant="success")
            yield Button("Reject", id="reject", variant="error")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        try:
            if event.button.id == "approve":
                self.client.approve_action(
                    self.request.id,
                    action_payload=self.request.action_payload,
                    idempotency_key=new_uuid7(),
                )
                self.query_one("#attention-status", Static).update("approved")
            elif event.button.id == "reject":
                reason = self.query_one("#reason", Input).value.strip()
                self.client.reject_action(
                    self.request.id, reason=reason, idempotency_key=new_uuid7()
                )
                self.query_one("#attention-status", Static).update("rejected")
        except AegisClientError as error:
            self.query_one("#attention-status", Static).update(f"error: {error.code}")
