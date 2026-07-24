"""Task detail screen: the full timeline for one task from a single response."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from aegis.client import AegisClientError


class TaskDetailScreen(Screen[None]):
    def __init__(self, client: Any, task_id: str, routing_reason: str = "") -> None:
        super().__init__()
        self.client = client
        self.task_id = task_id
        self.routing_reason = routing_reason

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static(self.task_id, id="task-id")
            yield Static(self.routing_reason, id="routing-reason")
            yield Static("", id="task-state")
            yield Static("", id="task-detail")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        try:
            task = self.client.get_task(self.task_id)
        except AegisClientError as error:
            self.query_one("#task-state", Static).update(f"error: {error.code}")
            return
        self.query_one("#task-state", Static).update(f"state: {task['state']} v{task['version']}")
        summary = (
            f"waits={len(task.get('waits', []))} "
            f"decisions={len(task.get('decisions', []))} "
            f"sessions={len(task.get('sessions', []))} "
            f"artifacts={len(task.get('artifacts', []))}"
        )
        self.query_one("#task-detail", Static).update(summary)
