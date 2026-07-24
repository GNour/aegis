"""Approvals display the exact digest and forward the exact payload/reason."""


async def _type(pilot, text: str) -> None:
    for ch in text:
        await pilot.press("space" if ch == " " else ch)


async def test_approval_requires_matching_digest(tui_app, pending_approval) -> None:
    async with tui_app.run_test() as pilot:
        tui_app.open_attention(pending_approval)
        await pilot.pause()
        digest_widget = tui_app.screen.query_one("#action-digest").renderable
        assert str(pending_approval.action_digest) in digest_widget
        await pilot.click("#approve")
        await pilot.pause()
        assert tui_app.client.approved[-1].action_digest == pending_approval.action_digest


async def test_reject_forwards_reason(tui_app, pending_approval) -> None:
    async with tui_app.run_test() as pilot:
        tui_app.open_attention(pending_approval)
        await pilot.pause()
        await pilot.click("#reason")
        await _type(pilot, "not now")
        await pilot.click("#reject")
        await pilot.pause()
        assert tui_app.client.rejected[-1].reason == "not now"


async def test_approval_shows_scope_risk_and_expiry(tui_app, pending_approval) -> None:
    async with tui_app.run_test() as pilot:
        tui_app.open_attention(pending_approval)
        await pilot.pause()
        assert "task.cancel" in tui_app.screen.query_one("#scope").renderable
        assert "high" in tui_app.screen.query_one("#risk").renderable
        assert "2026-07-24" in tui_app.screen.query_one("#expires").renderable
