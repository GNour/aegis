"""The Aegis operator TUI.

A Textual application whose only dependency is a typed control client (real
``AegisClient`` or a fake). Every screen calls named client methods; the TUI never
constructs a command or bypasses policy, approvals, or audit -- it is a view over the
same API the Hermes interface uses.
"""

from typing import Any

from textual.app import App
from textual.binding import Binding

from aegis.tui.screens.attention import AttentionScreen
from aegis.tui.screens.create_task import CreateTaskScreen
from aegis.tui.screens.task_detail import TaskDetailScreen
from aegis.tui.screens.tasks import TaskListScreen


class AegisTui(App[None]):
    BINDINGS = [
        Binding("n", "new_task", "New task"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, client: Any) -> None:
        super().__init__()
        self.client = client

    def on_mount(self) -> None:
        self.push_screen(TaskListScreen(self.client))

    def action_new_task(self) -> None:
        self.push_screen(CreateTaskScreen(self.client, on_created=self.open_task))

    def action_refresh(self) -> None:
        if isinstance(self.screen, TaskListScreen | TaskDetailScreen):
            self.screen.refresh_data()

    def open_task(self, task_id: str, routing_reason: str = "") -> None:
        self.push_screen(TaskDetailScreen(self.client, task_id, routing_reason=routing_reason))

    def open_attention(self, request: Any) -> None:
        self.push_screen(AttentionScreen(self.client, request))
