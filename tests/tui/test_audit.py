"""The audit screen reports chain verification, including the first mismatch."""


async def test_audit_ok_view(tui_app) -> None:
    async with tui_app.run_test() as pilot:
        tui_app.open_audit(lambda: {"ok": True, "checked": 10, "first_mismatch": None})
        await pilot.pause()
        status = tui_app.screen.query_one("#audit-status").renderable
        assert "ok" in status.lower()
        assert "10" in status


async def test_audit_mismatch_view(tui_app) -> None:
    async with tui_app.run_test() as pilot:
        tui_app.open_audit(lambda: {"ok": False, "checked": 5, "first_mismatch": "seq-3"})
        await pilot.pause()
        status = tui_app.screen.query_one("#audit-status").renderable
        assert "mismatch" in status.lower()
        assert "seq-3" in status
