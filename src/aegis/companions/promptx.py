"""Bounded, broker-only adapter for the PromptX ``aegis-contract`` command.

Built against PromptX's *actual* contract (verified against the pinned submodule):
``<node> <dist/cli/index.js> aegis-contract`` reads exactly one strict JSON request on
stdin and writes exactly one JSON response to stdout; discovery of filesystem, Git,
config, and providers is disabled inside the command itself (no ``--disable-*`` flags).
The CLI wires no provider, so ``brokered-refinement`` degrades to the deterministic
result until a broker is available — the deterministic context is always returned.

Guarantees: a verified executable digest and version before the first call; a fresh
child environment carrying only locale (and a loopback broker lease when present); a
bounded, timed subprocess; strict response parsing that rejects unknown or
authority-bearing keys; and exactly one safe audit record per terminal outcome, with
enrichment failing closed if that record cannot be written.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = "1"
MAX_RESPONSE_BYTES = 32 * 1024
TIMEOUT_SECONDS = 15
_SUCCESS_CODES = {"AEGIS_SUCCESS_DETERMINISTIC", "AEGIS_SUCCESS_BROKER_REFINED"}
_DEGRADED_CODE = "AEGIS_DEGRADED_BROKER_UNAVAILABLE"
_RESPONSE_KEYS = {"protocol_version", "outcome_code", "result", "diagnostics"}
# Authority-bearing keys must never appear anywhere in a PromptX response.
_FORBIDDEN_KEYS = frozenset(
    {"flow", "role", "model", "skills", "tools", "capabilities", "approval", "next_stage"}
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PromptXProtocolError(RuntimeError):
    """Raised on any digest/version/protocol/security violation. Carries no upstream body."""


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


class PromptXFact(StrictModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    value: str = Field(min_length=1, max_length=1024)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class BrokerLease(StrictModel):
    reference: str = Field(min_length=1, max_length=256)
    token: str = Field(min_length=1, max_length=4096)
    # Loopback HTTP only; anything else is rejected before a child is spawned.
    url: str = Field(pattern=r"^http://127\.0\.0\.1:\d{1,5}/[A-Za-z0-9/_.-]*$")


class PromptXRequest(StrictModel):
    mode: str = Field(pattern=r"^(deterministic-only|brokered-refinement)$")
    task_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    task_class: str = Field(min_length=1, max_length=64)
    metadata: Mapping[str, str] = Field(default_factory=dict)
    facts: tuple[PromptXFact, ...] = Field(min_length=1, max_length=32)

    def wire(self) -> dict[str, object]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "discovery_disabled": True,
            "mode": self.mode,
            "task": {
                "id": self.task_id,
                "task_class": self.task_class,
                "metadata": dict(self.metadata),
            },
            "facts": [
                {"name": f.name, "value": f.value, "source_digest": f.source_digest}
                for f in self.facts
            ],
        }


class PromptXResult(StrictModel):
    outcome_code: str
    additional_context: str
    task_class: str
    quality: str
    provider_state: str
    fact_digests: tuple[str, ...]
    degraded: bool
    duration_ms: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class PromptXAuditRecord(StrictModel):
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    fact_digests: tuple[str, ...] = Field(max_length=64)
    outcome_code: str = Field(max_length=64)
    degraded: bool
    duration_ms: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


def _scan_forbidden(node: object) -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key in _FORBIDDEN_KEYS:
                raise PromptXProtocolError("invalid PromptX response")
            _scan_forbidden(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _scan_forbidden(item)


def _digest_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class PromptXAdapter:
    def __init__(
        self,
        *,
        executable: Path,
        expected_sha256: str,
        expected_package_version: str,
        expected_protocol_version: str,
        run_process: Callable[..., ProcessResult],
        audit: Callable[[PromptXAuditRecord], None],
        node: str = "node",
        digest_file: Callable[[Path], str] = _digest_file,
    ) -> None:
        self._executable = executable
        self._expected_sha256 = expected_sha256
        self._expected_package_version = expected_package_version
        self._expected_protocol_version = expected_protocol_version
        self._run_process = run_process
        self._audit = audit
        self._node = node
        self._digest_file = digest_file
        self._ready = False

    # -- readiness -----------------------------------------------------------
    def _ensure_ready(self) -> None:
        if self._ready:
            return
        if self._digest_file(self._executable) != self._expected_sha256:
            raise PromptXProtocolError("promptx artifact digest mismatch")
        result = self._run_process(
            [self._node, str(self._executable), "aegis-contract", "--version-json"],
            input=b"",
            env=self._child_env(None),
            timeout=TIMEOUT_SECONDS,
        )
        payload = self._decode(result.stdout)
        if (
            payload.get("package_version") != self._expected_package_version
            or payload.get("protocol_version") != self._expected_protocol_version
        ):
            raise PromptXProtocolError("promptx version mismatch")
        self._ready = True

    # -- environment ---------------------------------------------------------
    def _child_env(self, broker: BrokerLease | None) -> dict[str, str]:
        env = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        if broker is not None:
            env["PROMPTX_BROKER_URL"] = broker.url
            env["PROMPTX_BROKER_TOKEN"] = broker.token
        return env

    # -- helpers -------------------------------------------------------------
    def _decode(self, stdout: bytes) -> dict[str, object]:
        if len(stdout) > MAX_RESPONSE_BYTES:
            raise PromptXProtocolError("invalid PromptX response")
        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            raise PromptXProtocolError("invalid PromptX response") from error
        if not isinstance(payload, dict):
            raise PromptXProtocolError("invalid PromptX response")
        return payload

    @staticmethod
    def _canonical(obj: object) -> bytes:
        return json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")

    def _failure_record(
        self, request: PromptXRequest, code: str
    ) -> PromptXAuditRecord:
        return PromptXAuditRecord(
            request_digest=sha256(self._canonical(request.wire())).hexdigest(),
            output_digest=None,
            fact_digests=tuple(f.source_digest for f in request.facts),
            outcome_code=code,
            degraded=True,
            duration_ms=0,
            input_tokens=0,
            output_tokens=0,
        )

    # -- main path -----------------------------------------------------------
    def enrich(
        self, request: PromptXRequest, *, broker: BrokerLease | None = None
    ) -> PromptXResult:
        try:
            self._ensure_ready()
            result, record = self._perform(request, broker)
        except PromptXProtocolError as error:
            self._audit(self._failure_record(request, code=self._code_for(error)))
            raise
        except subprocess.TimeoutExpired as error:
            self._audit(self._failure_record(request, code="AEGIS_ERROR_TIMEOUT"))
            raise PromptXProtocolError("promptx timed out") from error
        try:
            self._audit(record)
        except Exception as error:  # dispatch without an audit record is forbidden
            raise PromptXProtocolError("audit recording failed") from error
        return result

    @staticmethod
    def _code_for(error: PromptXProtocolError) -> str:
        return "AEGIS_ERROR_PROTOCOL"

    def _perform(
        self, request: PromptXRequest, broker: BrokerLease | None
    ) -> tuple[PromptXResult, PromptXAuditRecord]:
        wire = request.wire()
        payload = self._canonical(wire)
        request_digest = sha256(payload).hexdigest()
        result = self._run_process(
            [self._node, str(self._executable), "aegis-contract"],
            input=payload,
            env=self._child_env(broker),
            timeout=TIMEOUT_SECONDS,
        )
        response = self._decode(result.stdout)
        if set(response) - _RESPONSE_KEYS:
            raise PromptXProtocolError("invalid PromptX response")
        _scan_forbidden(response)
        if response.get("protocol_version") != PROTOCOL_VERSION:
            raise PromptXProtocolError("invalid PromptX response")
        outcome = response.get("outcome_code")
        if outcome not in _SUCCESS_CODES and outcome != _DEGRADED_CODE:
            raise PromptXProtocolError("promptx rejected request")

        result_block = response.get("result")
        diagnostics = response.get("diagnostics")
        if not isinstance(result_block, dict) or not isinstance(diagnostics, dict):
            raise PromptXProtocolError("invalid PromptX response")
        context = result_block.get("additional_context")
        if not isinstance(context, str) or not context:
            raise PromptXProtocolError("invalid PromptX response")

        tokens = diagnostics.get("token_usage", {})
        provider = diagnostics.get("provider", {})
        enriched = PromptXResult(
            outcome_code=str(outcome),
            additional_context=context,
            task_class=str(diagnostics.get("task_class", request.task_class)),
            quality=str(diagnostics.get("quality", "")),
            provider_state=str(provider.get("state", "unknown")),
            fact_digests=tuple(diagnostics.get("fact_digests", ())),
            degraded=(outcome == _DEGRADED_CODE),
            duration_ms=int(diagnostics.get("duration_ms", 0)),
            input_tokens=int(tokens.get("input_tokens", 0)),
            output_tokens=int(tokens.get("output_tokens", 0)),
        )
        record = PromptXAuditRecord(
            request_digest=request_digest,
            output_digest=sha256(context.encode("utf-8")).hexdigest(),
            fact_digests=enriched.fact_digests,
            outcome_code=enriched.outcome_code,
            degraded=enriched.degraded,
            duration_ms=enriched.duration_ms,
            input_tokens=enriched.input_tokens,
            output_tokens=enriched.output_tokens,
        )
        return enriched, record

    # -- test convenience ----------------------------------------------------
    @classmethod
    def for_fixture(cls, tmp_path: Path, fixture: Path) -> "PromptXAdapter":
        executable = tmp_path / "promptx"
        executable.write_bytes(b"stub")
        body = fixture.read_bytes()
        return cls(
            executable=executable,
            expected_sha256=sha256(b"stub").hexdigest(),
            expected_package_version="1.0.0-aegis.0",
            expected_protocol_version=PROTOCOL_VERSION,
            run_process=lambda *a, **k: ProcessResult(0, body, b""),
            audit=lambda _record: None,
            digest_file=lambda _path: sha256(b"stub").hexdigest(),
        )
