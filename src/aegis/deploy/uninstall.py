"""Scoped uninstall.

Uninstall removes only the appliance's labeled Compose project and preserves durable data
by default. Purging data requires explicit confirmation and resolved-path validation
against allowed roots, so a stray or crafted path can never delete unrelated files. No
lifecycle command runs a global Docker prune.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from aegis.deploy.runtime import ContainerRuntime


@dataclass(frozen=True)
class UninstallResult:
    removed_project: str
    purged_paths: list[Path]
    preserved_paths: list[Path]


def _under_allowed_root(path: Path, allowed_roots: list[Path]) -> bool:
    resolved = path.resolve()
    return any(resolved.is_relative_to(Path(root).resolve()) for root in allowed_roots)


def uninstall(
    runtime: ContainerRuntime,
    project: str,
    *,
    data_paths: list[Path],
    allowed_roots: list[Path],
    purge_data: bool = False,
    confirm: bool = False,
) -> UninstallResult:
    # Remove only this labeled project; never a global prune.
    runtime.down(project)

    if not purge_data:
        return UninstallResult(project, purged_paths=[], preserved_paths=list(data_paths))

    if not confirm:
        raise ValueError("purging data requires explicit confirmation")

    for path in data_paths:
        if not _under_allowed_root(Path(path), allowed_roots):
            raise ValueError(f"refusing to purge path outside allowed roots: {path}")

    purged: list[Path] = []
    for path in data_paths:
        target = Path(path)
        if target.exists():
            shutil.rmtree(target)
        purged.append(target)
    return UninstallResult(project, purged_paths=purged, preserved_paths=[])
