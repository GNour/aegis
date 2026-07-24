"""Audit screen: verify the hash-linked ledger and report the first mismatch."""

from collections.abc import Callable
from typing import Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class AuditScreen(Screen[None]):
    def __init__(self, verifier: Callable[[], dict[str, Any]]) -> None:
        super().__init__()
        self._verifier = verifier

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="audit-status")
        yield Footer()

    def on_mount(self) -> None:
        result = self._verifier()
        if result.get("ok"):
            self.query_one("#audit-status", Static).update(
                f"OK: verified {result.get('checked', 0)} events"
            )
        else:
            self.query_one("#audit-status", Static).update(
                f"MISMATCH at {result.get('first_mismatch')} "
                f"(checked {result.get('checked', 0)})"
            )
