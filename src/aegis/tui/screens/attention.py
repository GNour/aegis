"""Attention screen: decisions and one-use approvals (Task 3 expands this)."""

from typing import Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static  # placeholder; replaced in Task 3


class AttentionScreen(Screen[None]):  # pragma: no cover - expanded in Task 3
    def __init__(self, client: Any, request: Any) -> None:
        super().__init__()
        self.client = client
        self.request = request

    def compose(self) -> ComposeResult:
        yield Static("")
