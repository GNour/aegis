"""The operator can create a task and open its detail view from the keyboard."""

import pytest

from aegis.tui.screens.task_detail import TaskDetailScreen
from aegis.tui.screens.tasks import TaskListScreen


async def _type(pilot, text: str) -> None:
    # Textual's Pilot enters text via key presses; spaces are the "space" key.
    for ch in text:
        await pilot.press("space" if ch == " " else ch)


async def test_operator_creates_and_opens_task(tui_app, fake_client) -> None:
    async with tui_app.run_test() as pilot:
        await pilot.press("n")
        await pilot.click("#project")
        await _type(pilot, "demo")
        await pilot.click("#request")
        await _type(pilot, "add health route")
        await pilot.click("#submit")
        await pilot.pause()
        assert fake_client.created[0].project_id == "demo"
        assert fake_client.created[0].request == "add health route"
        assert isinstance(tui_app.screen, TaskDetailScreen)
        assert tui_app.screen.query_one("#task-id").renderable == "task-001"


async def test_task_list_is_the_initial_screen(tui_app) -> None:
    async with tui_app.run_test():
        assert isinstance(tui_app.screen, TaskListScreen)


async def test_routing_reason_is_shown_after_creation(tui_app, fake_client) -> None:
    async with tui_app.run_test() as pilot:
        await pilot.press("n")
        await pilot.click("#project")
        await _type(pilot, "demo")
        await pilot.click("#request")
        await _type(pilot, "x")
        await pilot.click("#submit")
        await pilot.pause()
        detail = tui_app.screen
        assert "matched auto rule" in detail.query_one("#routing-reason").renderable


async def test_detail_handles_get_error_without_crashing(tui_app, fake_client) -> None:
    fake_client.fail_get = True
    async with tui_app.run_test() as pilot:
        await pilot.press("n")
        await pilot.click("#project")
        await _type(pilot, "demo")
        await pilot.click("#request")
        await _type(pilot, "x")
        await pilot.click("#submit")
        await pilot.pause()
        detail = tui_app.screen
        assert isinstance(detail, TaskDetailScreen)
        assert "error" in detail.query_one("#task-state").renderable.lower()


@pytest.mark.parametrize("key", ["n", "r", "q"])
def test_core_bindings_exist(key) -> None:
    from aegis.tui.app import AegisTui

    keys = {binding.key for binding in AegisTui.BINDINGS}
    assert key in keys
