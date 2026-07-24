"""Create-task screen: choose routing and submit through the typed client."""

from collections.abc import Callable
from typing import Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Input, Label

from aegis.client import AegisClientError
from aegis.domain.ids import new_uuid7


class CreateTaskScreen(Screen[None]):
    def __init__(self, client: Any, on_created: Callable[[str, str], None]) -> None:
        super().__init__()
        self.client = client
        self._on_created = on_created

    def compose(self) -> ComposeResult:
        yield Label("New task", id="title")
        yield Input(placeholder="project id", id="project")
        yield Input(placeholder="request", id="request")
        yield Input(value="auto", placeholder="flow id (or 'auto')", id="flow")
        yield Button("Submit", id="submit", variant="primary")
        yield Label("", id="error")

    def on_mount(self) -> None:
        try:
            self.client.list_flows()
        except AegisClientError:
            self.query_one("#error", Label).update("could not load flows")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "submit":
            return
        project = self.query_one("#project", Input).value.strip()
        request = self.query_one("#request", Input).value.strip()
        flow = self.query_one("#flow", Input).value.strip() or "auto"
        try:
            result = self.client.create_task(
                project_id=project,
                request=request,
                flow_id=flow,
                idempotency_key=new_uuid7(),
            )
        except AegisClientError as error:
            self.query_one("#error", Label).update(f"error: {error.code}")
            return
        self._on_created(result["task_id"], str(result.get("routing_reason", "")))
