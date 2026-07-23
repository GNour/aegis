# TUI and Hermes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the operator a complete local TUI and a restricted Hermes/Telegram interface that share the same API, policy, approval, and audit behavior.

**Architecture:** A typed UDS client is the only interface dependency. Textual renders the full operator surface. The Hermes plugin validates Telegram identity, signs bounded requests, and exposes nine functions; its skill contains conversational policy but no capabilities.

**Tech Stack:** Python 3.12, HTTPX UDS transport, Textual, Hermes Python plugin SDK, pytest, snapshot tests

---

### Task 1: Typed Unix-socket client

**Files:**
- Create: `src/aegis/client.py`
- Create: `tests/contract/test_control_client.py`

- [ ] **Step 1: Write serialization and stable-error tests**

```python
def test_create_task_sends_idempotency_and_assertion(fake_api, client) -> None:
    client.create_task(project_id="demo", request="fix login", flow_id="auto", idempotency_key="k1")
    request = fake_api.last_request
    assert request.headers["Idempotency-Key"] == "k1"
    assert request.headers["X-Aegis-Principal"]
    assert request.json()["flow_id"] == "auto"


def test_error_code_is_preserved(fake_api, client) -> None:
    fake_api.respond(409, {"error": {"code": "state_conflict", "message": "changed"}, "meta": {"request_id": "r1"}})
    with pytest.raises(AegisClientError) as error:
        client.resume_task("t1", expected_version=2)
    assert error.value.code == "state_conflict"
```

- [ ] **Step 2: Run and confirm client absence**

Run: `uv run pytest tests/contract/test_control_client.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Implement the bounded client**

```python
import httpx


class AegisClientError(RuntimeError):
    def __init__(self, code: str, message: str, request_id: str) -> None:
        super().__init__(message)
        self.code, self.request_id = code, request_id


class AegisClient:
    def __init__(self, socket_path: str, signer) -> None:
        self.http = httpx.Client(transport=httpx.HTTPTransport(uds=socket_path), base_url="http://aegis", timeout=10.0)
        self.signer = signer

    def request(self, method: str, path: str, body: dict, idempotency_key: str | None = None) -> dict:
        headers = {"X-Aegis-Principal": self.signer.sign(method, path, body)}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        response = self.http.request(method, path, json=body, headers=headers)
        payload = response.json()
        if response.is_error:
            raise AegisClientError(payload["error"]["code"], payload["error"]["message"], payload["meta"]["request_id"])
        return payload["data"]
```

Add one named method for each FR-001 operation. Methods accept typed request
models and return typed response models; none accepts a command string.

- [ ] **Step 4: Run all client contract tests**

Run: `uv run pytest tests/contract/test_control_client.py -q`

Expected: all nine operations, timeout mapping, response bounds, and stable errors pass.

- [ ] **Step 5: Commit the shared client**

```bash
git add src/aegis/client.py tests/contract/test_control_client.py
git commit -m "feat(client): add typed local control api client"
```

### Task 2: Textual task list, task detail, and creation flow

**Files:**
- Create: `src/aegis/tui/app.py`
- Create: `src/aegis/tui/screens/tasks.py`
- Create: `src/aegis/tui/screens/task_detail.py`
- Create: `src/aegis/tui/screens/create_task.py`
- Create: `tests/tui/test_task_workflow.py`

- [ ] **Step 1: Write the operator workflow test**

```python
async def test_operator_creates_and_opens_task(tui_app, fake_client) -> None:
    async with tui_app.run_test() as pilot:
        await pilot.press("n")
        await pilot.click("#project")
        await pilot.type("demo")
        await pilot.click("#request")
        await pilot.type("add health route")
        await pilot.click("#submit")
        assert fake_client.created[0].project_id == "demo"
        assert tui_app.screen.query_one("#task-id").renderable == "task-001"
```

- [ ] **Step 2: Run and confirm missing TUI**

Run: `uv run pytest tests/tui/test_task_workflow.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Implement the three screens**

```python
from textual.app import App
from textual.binding import Binding


class AegisTui(App):
    BINDINGS = [Binding("n", "new_task", "New task"), Binding("r", "refresh", "Refresh"), Binding("q", "quit", "Quit")]

    def __init__(self, client) -> None:
        super().__init__()
        self.client = client

    def on_mount(self) -> None:
        self.push_screen(TaskListScreen(self.client))

    def action_new_task(self) -> None:
        self.push_screen(CreateTaskScreen(self.client, on_created=self.open_task))

    def open_task(self, task_id: str) -> None:
        self.push_screen(TaskDetailScreen(self.client, task_id))
```

`TaskListScreen` renders task ID/project/state/flow/risk/attention. `CreateTaskScreen`
loads `list_flows`, supports explicit/auto routing, and shows the returned routing
reason. `TaskDetailScreen` renders stages, attempts, waits, decisions, approvals,
sessions, services, budgets, artifacts, and knowledge receipts from one response.

- [ ] **Step 4: Run TUI snapshots and keyboard tests**

Run: `uv run pytest tests/tui/test_task_workflow.py tests/tui/test_snapshots.py -q`

Expected: create/open/refresh, empty/error/loading, and bounded-log snapshots pass.

- [ ] **Step 5: Commit the basic TUI**

```bash
git add src/aegis/tui tests/tui
git commit -m "feat(tui): add task creation and timeline views"
```

### Task 3: TUI decisions, approvals, recovery, and audit views

**Files:**
- Create: `src/aegis/tui/screens/attention.py`
- Create: `src/aegis/tui/screens/audit.py`
- Create: `tests/tui/test_attention.py`

- [ ] **Step 1: Write exact-approval display test**

```python
async def test_approval_requires_matching_digest(tui_app, pending_approval) -> None:
    async with tui_app.run_test() as pilot:
        tui_app.open_attention(pending_approval)
        assert str(pending_approval.action_digest) in tui_app.screen.render()
        await pilot.click("#approve")
        assert tui_app.client.approved[-1].action_digest == pending_approval.action_digest
```

- [ ] **Step 2: Run and observe missing screen**

Run: `uv run pytest tests/tui/test_attention.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Implement operator controls**

```python
class AttentionScreen(Screen):
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approve":
            self.client.approve_action(self.request.id, action_digest=self.request.action_digest)
        elif event.button.id == "reject":
            self.client.reject_action(self.request.id, reason=self.query_one("#reason", Input).value)
```

Render question/options/evidence for decisions and digest/scope/risk/expiry/effect
for approvals. Add pause/resume/cancel controls, audit-chain verification, config
validation/simulation, and a controlled Herdr attachment command that opens a new
local terminal only for an authorized session ID returned by Aegis.

- [ ] **Step 4: Run attention and audit tests**

Run: `uv run pytest tests/tui/test_attention.py tests/tui/test_audit.py -q`

Expected: decision, approve, reject, resume, cancel, replay-error, expired, and audit mismatch views pass.

- [ ] **Step 5: Commit full operator controls**

```bash
git add src/aegis/tui tests/tui
git commit -m "feat(tui): add decisions recovery and audit controls"
```

### Task 4: Hermes `company-control` plugin

**Files:**
- Create: `integrations/hermes/plugin/company_control.py`
- Create: `integrations/hermes/plugin/manifest.yaml`
- Create: `integrations/hermes/tests/test_company_control.py`

- [ ] **Step 1: Write allowlist and tool-surface tests**

```python
EXPECTED_TOOLS = {"list_flows", "create_task", "get_task_status", "approve_action", "reject_action", "cancel_task", "resume_task", "capture_note", "schedule_reminder"}


def test_plugin_exposes_only_typed_tools(plugin) -> None:
    assert set(plugin.tools) == EXPECTED_TOOLS


def test_unknown_telegram_user_is_rejected(plugin) -> None:
    with pytest.raises(PermissionError, match="telegram user not allowed"):
        plugin.create_task(context={"telegram_user_id": 999}, project_id="demo", request="x", flow_id="auto")
```

- [ ] **Step 2: Run plugin tests and confirm absence**

Run: `uv run pytest integrations/hermes/tests/test_company_control.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Implement identity mapping and bounded calls**

```python
class CompanyControlPlugin:
    def __init__(self, client, allowed_users: dict[int, str]) -> None:
        self.client, self.allowed_users = client, allowed_users
        self.tools = {name: getattr(self, name) for name in EXPECTED_TOOLS}

    def actor(self, context: dict[str, object]) -> str:
        telegram_id = int(context["telegram_user_id"])
        if telegram_id not in self.allowed_users:
            raise PermissionError("telegram user not allowed")
        return self.allowed_users[telegram_id]

    def create_task(self, context, project_id: str, request: str, flow_id: str = "auto") -> dict:
        actor = self.actor(context)
        return self.client.for_actor(actor, "telegram").create_task(project_id=project_id, request=request, flow_id=flow_id)
```

Implement the other eight methods as direct typed client calls. Bound request/note
lengths, reject control characters, never accept command or arbitrary argument
fields, and render responses below the Telegram message-size ceiling.

- [ ] **Step 4: Run plugin and API-parity tests**

Run: `uv run pytest integrations/hermes/tests tests/integration/interfaces/test_api_parity.py -q`

Expected: allowlist, exact tool set, bounded inputs, approval digest, and TUI/Telegram audit parity pass.

- [ ] **Step 5: Commit the Hermes plugin**

```bash
git add integrations/hermes/plugin integrations/hermes/tests tests/integration/interfaces
git commit -m "feat(hermes): expose typed company control tools"
```

### Task 5: Hermes `company-orchestrator` skill and notification delivery

**Files:**
- Create: `integrations/hermes/skill/SKILL.md`
- Create: `src/aegis/notifications.py`
- Create: `integrations/hermes/tests/test_skill_contract.py`
- Create: `tests/unit/test_notifications.py`

- [ ] **Step 1: Write skill and idempotent-delivery tests**

```python
def test_skill_names_no_shell_capability(skill_text) -> None:
    assert "company-control" in skill_text
    assert "remote shell" in skill_text
    assert "start_process" not in skill_text
    assert "execute arbitrary" not in skill_text


def test_duplicate_attention_event_delivers_once(notifier, telegram) -> None:
    notifier.deliver(event_id="e1", actor_id="owner", message="Approval A1 needs review")
    notifier.deliver(event_id="e1", actor_id="owner", message="Approval A1 needs review")
    assert len(telegram.messages) == 1
```

- [ ] **Step 2: Confirm tests fail**

Run: `uv run pytest integrations/hermes/tests/test_skill_contract.py tests/unit/test_notifications.py -q`

Expected: FAIL because files/services are absent.

- [ ] **Step 3: Write the skill contract and notifier**

The skill must instruct Hermes to call `list_flows`, clarify missing project/outcome,
report the server's routing explanation, identify a pending approval by stable ID,
surface prohibited actions to the human, and never reinterpret a message as a host
command. Add examples for create/status/decision/approve/reject/cancel/resume/note/reminder.

```python
class NotificationService:
    def deliver(self, event_id: str, actor_id: str, message: str) -> None:
        if self.store.delivery_exists(event_id, actor_id):
            return
        result = self.transport.send(actor_id, message[:3500])
        self.store.record_delivery(event_id, actor_id, result.message_id, result.status)
```

- [ ] **Step 4: Run all interface verification**

Run: `uv run pytest tests/tui integrations/hermes/tests tests/integration/interfaces tests/unit/test_notifications.py -q`

Expected: TUI and Telegram success/error/approval/recovery paths create equivalent API calls and audit events.

- [ ] **Step 5: Commit interfaces**

```bash
git add integrations/hermes src/aegis/notifications.py tests
git commit -m "feat(interfaces): complete tui and telegram supervision"
```
