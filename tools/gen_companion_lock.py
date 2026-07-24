#!/usr/bin/env python3
"""Generate config/companions.lock.json from the pinned submodules.

Reads each companion's checked-out commit and version command, computes the artifact
and SBOM digests deterministically, and writes the canonical lock. Never hand-enter a
digest or version. Run from the aegis repo root:

    uv run python tools/gen_companion_lock.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aegis.companions.digests import artifact_sha256, build_sbom, sbom_sha256  # noqa: E402
from aegis.companions.lock import CompanionLock, verify_sources  # noqa: E402

SOURCE_URLS = {
    "promptx": "https://github.com/GNour/promptx.git",
    "subagents": "https://github.com/GNour/subagents.git",
}


def git_head(path: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def promptx_version(path: Path) -> tuple[str, str]:
    out = subprocess.run(
        ["node", str(path / "dist" / "cli" / "index.js"), "aegis-contract", "--version-json"],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(out.stdout)
    return data["package_version"], data["protocol_version"]


def subagents_version(path: Path) -> tuple[str, str]:
    out = subprocess.run(
        [str(path / "bin" / "subagents-catalog"), "version", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(out.stdout)
    return data["package_version"], data["catalog_schema_version"]


def package_entry(name: str, artifact_dir: Path) -> dict[str, object]:
    path = ROOT / "packages" / name
    commit = git_head(path)
    if name == "promptx":
        version, contract = promptx_version(path)
    else:
        version, contract = subagents_version(path)
    artifact_digest = artifact_sha256(artifact_dir)
    sbom = build_sbom(
        name=name,
        version=version,
        source_url=SOURCE_URLS[name],
        source_commit=commit,
        license_spdx="MIT",
        artifact_digest=artifact_digest,
    )
    return {
        "path": f"packages/{name}",
        "source_url": SOURCE_URLS[name],
        "source_commit": commit,
        "package_version": version,
        "contract_version": contract,
        "artifact_sha256": artifact_digest,
        "sbom_sha256": sbom_sha256(sbom),
        "license_spdx": "MIT",
    }


def main() -> int:
    lock_data = {
        "schema_version": 1,
        "promptx": package_entry("promptx", ROOT / "packages" / "promptx" / "dist"),
        "subagents": package_entry("subagents", ROOT / "packages" / "subagents" / "dist"),
    }
    lock = CompanionLock.model_validate(lock_data)  # fail closed on any bad field
    verify_sources(ROOT, lock, require_present=True)
    out_path = ROOT / "config" / "companions.lock.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(lock_data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
