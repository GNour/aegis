"""Task list screen: an at-a-glance table of known tasks."""

from typing import Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header


class TaskListScreen(Screen[None]):
    def __init__(self, client: Any) -> None:
        super().__init__()
        self.client = client

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="tasks")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#tasks", DataTable)
        table.add_columns("task", "project", "state", "flow", "risk", "attention")
        self.refresh_data()

    def refresh_data(self) -> None:
        # The control API exposes tasks by id; the list view holds what this session
        # has opened. A durable index arrives with the persistence work in a later plan.
        pass

    def add_task_row(self, task_id: str, project: str, state: str, flow: str, risk: str) -> None:
        table = self.query_one("#tasks", DataTable)
        table.add_row(task_id, project, state, flow, risk, "")
