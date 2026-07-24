"""Parse, cross-validate, and compile the versioned configuration catalog.

Loading proceeds in two phases: parse every document under a config root with strict
Pydantic models (Task 5 models.py), then cross-resolve every reference (model alias,
capability profile, role, stage, flow, routing target) and reject unresolved
references, version-too-old references, and fallback cycles. The compiled ``Catalog``
is immutable; ``CatalogManager`` builds a brand-new one and swaps it under one lock
only after the whole build succeeds, so a half-built catalog can never be observed and
an active task's stored snapshot is never affected by a failed or successful reload.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self, cast

import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError

from aegis.config.models import (
    CapabilityProfileDoc,
    FlowDoc,
    ModelAliasesDoc,
    RoleDoc,
    RoutingDoc,
    StageDoc,
)
from aegis.domain.models import FrozenJsonMapping

_FROZEN_JSON_ADAPTER: TypeAdapter[Any] = TypeAdapter(FrozenJsonMapping)


class CatalogError(ValueError):
    """Raised for any invalid, unresolved, cyclic, or malformed catalog input."""


def _load_yaml_mapping(path: Path) -> Mapping[str, object]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise CatalogError(f"{path.name}: invalid YAML") from error
    if not isinstance(data, Mapping):
        raise CatalogError(f"{path.name}: document must be a mapping")
    return data


def _document_hash(model: BaseModel) -> str:
    payload = json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate(model_cls: type[BaseModel], data: Mapping[str, object], *, where: str) -> Any:
    try:
        return model_cls.model_validate(data)
    except ValidationError as error:
        raise CatalogError(f"{where}: {error}") from error


def _load_documents(directory: Path, model_cls: type[BaseModel]) -> dict[str, Any]:
    items: dict[str, Any] = {}
    if not directory.is_dir():
        return items
    for path in sorted(directory.glob("*.yaml")):
        doc = _validate(model_cls, _load_yaml_mapping(path), where=path.name)
        doc_id = doc.id
        if doc_id != path.stem:
            raise CatalogError(f"{path.name}: document id {doc_id!r} must match filename")
        if doc_id in items:
            raise CatalogError(f"duplicate {model_cls.__name__} id: {doc_id}")
        items[doc_id] = doc
    return items


def _detect_self_reference_cycle(edges: Mapping[str, str | None], *, kind: str) -> None:
    """Detect a cycle in a fallback graph where each node has at most one out-edge."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(edges, WHITE)

    def visit(node: str) -> None:
        color[node] = GRAY
        nxt = edges.get(node)
        if nxt is not None and nxt in edges:
            if color.get(nxt) == GRAY:
                raise CatalogError(f"cyclic {kind} fallback: {node} -> {nxt}")
            if color.get(nxt) == WHITE:
                visit(nxt)
        color[node] = BLACK

    for node in list(edges):
        if color[node] == WHITE:
            visit(node)


def _frozen(payload: dict[str, object]) -> Mapping[str, object]:
    return cast("Mapping[str, object]", _FROZEN_JSON_ADAPTER.validate_python(payload))


@dataclass(frozen=True)
class CompiledStage:
    doc: StageDoc

    def snapshot(self) -> Mapping[str, object]:
        return _frozen(
            {
                "stage_id": self.doc.id,
                "stage_version": self.doc.version,
                "role_id": self.doc.role.id,
                "model_alias": self.doc.model_alias,
                "skills": [f"{skill.id}@{skill.version}" for skill in self.doc.skills],
                "capability_profile": self.doc.capability_profile.id,
                "budgets": self.doc.budgets.model_dump(mode="json"),
                "decision_required": self.doc.decision_required,
                "approval_required": self.doc.approval_required,
                "resume_supported": self.doc.resume_supported,
                "knowledge_required": self.doc.knowledge_required,
                "cleanup_gate": self.doc.cleanup_gate,
            }
        )


@dataclass(frozen=True)
class CompiledFlow:
    doc: FlowDoc
    doc_hash: str
    stages: tuple[CompiledStage, ...]

    def snapshot(self) -> Mapping[str, object]:
        return _frozen(
            {
                "flow_id": self.doc.id,
                "flow_version": self.doc.version,
                "flow_hash": self.doc_hash,
                "allowed_callers": list(self.doc.allowed_callers),
                "accepted_intents": list(self.doc.accepted_intents),
                "gates": list(self.doc.gates),
                "completion_policy": self.doc.completion_policy,
                "stages": [dict(stage.snapshot()) for stage in self.stages],
            }
        )


@dataclass(frozen=True)
class Catalog:
    model_aliases_doc: ModelAliasesDoc
    capability_profiles: Mapping[str, CapabilityProfileDoc]
    roles: Mapping[str, RoleDoc]
    stages: Mapping[str, StageDoc]
    flows: Mapping[str, CompiledFlow]
    routing: RoutingDoc
    canonical_hash: str

    def flow(self, flow_id: str) -> CompiledFlow:
        try:
            return self.flows[flow_id]
        except KeyError:
            raise CatalogError(f"unknown flow: {flow_id}") from None

    def role(self, role_id: str) -> RoleDoc:
        try:
            return self.roles[role_id]
        except KeyError:
            raise CatalogError(f"unknown role: {role_id}") from None

    def stage(self, stage_id: str) -> StageDoc:
        try:
            return self.stages[stage_id]
        except KeyError:
            raise CatalogError(f"unknown stage: {stage_id}") from None

    def capability_profile(self, profile_id: str) -> CapabilityProfileDoc:
        try:
            return self.capability_profiles[profile_id]
        except KeyError:
            raise CatalogError(f"unknown capability profile: {profile_id}") from None

    def model_alias(self, alias_id: str) -> str:
        if alias_id not in self.model_aliases_doc.aliases:
            raise CatalogError(f"unknown model alias: {alias_id}")
        return alias_id


def build_catalog(root: Path) -> Catalog:
    """Parse and cross-validate every document under ``root``. Fails closed."""
    models_path = root / "models.yaml"
    if not models_path.is_file():
        raise CatalogError("missing models.yaml")
    model_aliases_doc = _validate(
        ModelAliasesDoc, _load_yaml_mapping(models_path), where="models.yaml"
    )

    capability_profiles = _load_documents(root / "capabilities", CapabilityProfileDoc)
    roles = _load_documents(root / "roles", RoleDoc)
    stages = _load_documents(root / "stages", StageDoc)
    flow_docs = _load_documents(root / "flows", FlowDoc)

    routing_path = root / "routing.yaml"
    if not routing_path.is_file():
        raise CatalogError("missing routing.yaml")
    routing = _validate(RoutingDoc, _load_yaml_mapping(routing_path), where="routing.yaml")

    def _check_alias(alias_id: str, where: str) -> None:
        if alias_id not in model_aliases_doc.aliases:
            raise CatalogError(f"{where}: unresolved model alias {alias_id}")

    def _check_capability(ref_id: str, min_version: int, where: str) -> None:
        profile = capability_profiles.get(ref_id)
        if profile is None:
            raise CatalogError(f"{where}: unresolved capability profile {ref_id}")
        if profile.version < min_version:
            raise CatalogError(f"{where}: capability profile {ref_id} below min_version")

    for role_id, role in roles.items():
        _check_alias(role.model_alias, f"role {role_id}")
        _check_capability(
            role.capability_profile.id, role.capability_profile.min_version, f"role {role_id}"
        )

    for stage_id, stage in stages.items():
        role = roles.get(stage.role.id)
        if role is None:
            raise CatalogError(f"stage {stage_id}: unresolved role {stage.role.id}")
        if role.version < stage.role.min_version:
            raise CatalogError(f"stage {stage_id}: role {stage.role.id} below min_version")
        _check_alias(stage.model_alias, f"stage {stage_id}")
        _check_capability(
            stage.capability_profile.id, stage.capability_profile.min_version, f"stage {stage_id}"
        )
        if stage.fallback_stage is not None and stage.fallback_stage not in stages:
            raise CatalogError(f"stage {stage_id}: unresolved fallback stage {stage.fallback_stage}")

    _detect_self_reference_cycle(
        {stage_id: stage.fallback_stage for stage_id, stage in stages.items()}, kind="stage"
    )

    for flow_id, flow in flow_docs.items():
        for stage_ref in flow.stages:
            stage = stages.get(stage_ref.id)
            if stage is None:
                raise CatalogError(f"flow {flow_id}: unresolved stage {stage_ref.id}")
            if stage.version < stage_ref.min_version:
                raise CatalogError(f"flow {flow_id}: stage {stage_ref.id} below min_version")
        if flow.fallback_flow is not None and flow.fallback_flow not in flow_docs:
            raise CatalogError(f"flow {flow_id}: unresolved fallback flow {flow.fallback_flow}")

    _detect_self_reference_cycle(
        {flow_id: flow.fallback_flow for flow_id, flow in flow_docs.items()}, kind="flow"
    )

    for rule in routing.rules:
        if rule.select_flow is not None and rule.select_flow not in flow_docs:
            raise CatalogError(f"routing rule {rule.id}: unresolved flow {rule.select_flow}")

    compiled_flows: dict[str, CompiledFlow] = {}
    doc_hashes: dict[str, str] = {}
    for flow_id, flow in flow_docs.items():
        compiled_stages = tuple(CompiledStage(stages[ref.id]) for ref in flow.stages)
        flow_hash = _document_hash(flow)
        doc_hashes[flow_id] = flow_hash
        compiled_flows[flow_id] = CompiledFlow(flow, flow_hash, compiled_stages)

    entries: list[dict[str, object]] = [
        {"kind": "models", "id": model_aliases_doc.id, "version": model_aliases_doc.version,
         "hash": _document_hash(model_aliases_doc)},
        {"kind": "routing", "id": routing.id, "version": routing.version,
         "hash": _document_hash(routing)},
    ]
    for kind, docs in (
        ("capability", capability_profiles),
        ("role", roles),
        ("stage", stages),
    ):
        for doc_id, doc in docs.items():
            entries.append(
                {"kind": kind, "id": doc_id, "version": doc.version, "hash": _document_hash(doc)}
            )
    for flow_id, flow in flow_docs.items():
        entries.append(
            {"kind": "flow", "id": flow_id, "version": flow.version, "hash": doc_hashes[flow_id]}
        )
    entries.sort(key=lambda entry: (str(entry["kind"]), str(entry["id"])))
    canonical_hash = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()

    return Catalog(
        model_aliases_doc=model_aliases_doc,
        capability_profiles=capability_profiles,
        roles=roles,
        stages=stages,
        flows=compiled_flows,
        routing=routing,
        canonical_hash=canonical_hash,
    )


class CatalogManager:
    """Owns the current compiled catalog and atomically swaps it on a valid reload."""

    def __init__(self, root: Path, catalog: Catalog) -> None:
        self._root = root
        self._lock = threading.Lock()
        self._current = catalog

    @property
    def current(self) -> Catalog:
        return self._current

    @classmethod
    def load(cls, root: Path) -> Self:
        return cls(root, build_catalog(root))

    def reload(self) -> bool:
        """Build a complete new catalog and swap it only if the build succeeds."""
        try:
            new_catalog = build_catalog(self._root)
        except CatalogError:
            return False
        with self._lock:
            self._current = new_catalog
        return True
