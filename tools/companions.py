#!/usr/bin/env python3
"""Companion build/check commands for maintainers and CI.

    uv run python tools/companions.py compile-subagents [--check]

``compile-subagents`` compiles the pinned Subagents catalog with the reviewed role
mappings and writes the embedded release assets under src/aegis/data/companions/. With
``--check`` it compares bytes and fails without writing, so CI catches drift.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from aegis.companions.catalog import build_provenance, compile_catalog  # noqa: E402
from aegis.companions.subagents import RoleMappings, SubagentsCatalog  # noqa: E402

CATALOG_SRC = ROOT / "packages" / "subagents" / "dist" / "catalog.json"
MAPPINGS_SRC = ROOT / "config" / "companions" / "role-mappings.yaml"
DATA_DIR = ROOT / "src" / "aegis" / "data" / "companions"
COMPILED_PATH = DATA_DIR / "roles.compiled.json"
PROVENANCE_PATH = DATA_DIR / "roles.provenance.json"


def _canonical_text(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _compile() -> tuple[str, str]:
    source = SubagentsCatalog.model_validate_json(
        CATALOG_SRC.read_text(encoding="utf-8")
    )
    mappings = RoleMappings.model_validate(
        yaml.safe_load(MAPPINGS_SRC.read_text(encoding="utf-8"))
    )
    result = compile_catalog(source, mappings)
    compiled_text = _canonical_text(result.catalog.model_dump(mode="json"))
    provenance_text = _canonical_text(build_provenance(source, result))
    return compiled_text, provenance_text


def cmd_compile_subagents(check: bool) -> int:
    compiled_text, provenance_text = _compile()
    targets = {COMPILED_PATH: compiled_text, PROVENANCE_PATH: provenance_text}
    if check:
        drift = [
            path
            for path, text in targets.items()
            if (path.read_text(encoding="utf-8") if path.exists() else "") != text
        ]
        if drift:
            names = ", ".join(str(p.relative_to(ROOT)) for p in drift)
            print(f"compiled assets out of date ({names})", file=sys.stderr)
            return 1
        print("compiled catalog assets are up to date")
        return 0
    for path, text in targets.items():
        _write_atomic(path, text)
    print(f"wrote {COMPILED_PATH.relative_to(ROOT)} and {PROVENANCE_PATH.relative_to(ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="companions")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile-subagents", help="compile the reviewed catalog")
    compile_p.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "compile-subagents":
        return cmd_compile_subagents(args.check)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
