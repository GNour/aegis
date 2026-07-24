"""Render rootless container launch arguments from a WorkerSpec.

The launch adapter builds an explicit argument array directly from the immutable
`WorkerSpec`. It passes only the spec's environment (never `--env-host` or a bare
`-e KEY` that would inherit a host variable), forces network isolation, drops all
capabilities, disables privilege escalation, and mounts a read-only root.
"""

from collections.abc import Iterable

from aegis.execution.workers import WorkerSpec


def render_run_args(spec: WorkerSpec, *, context: str = "aegis-rootless") -> list[str]:
    argv: list[str] = ["docker", "--context", context, "run", "--rm"]
    argv += ["--network", spec.network]
    for capability in spec.cap_drop:
        argv += ["--cap-drop", capability]
    if spec.no_new_privileges:
        argv += ["--security-opt", "no-new-privileges:true"]
    if spec.read_only_root:
        argv += ["--read-only"]
    argv += ["--memory", f"{spec.memory_mb}m", "--cpus", str(spec.cpus)]
    for key, value in spec.environment.items():
        argv += ["--env", f"{key}={value}"]
    for source, target, mode in spec.mounts:
        argv += ["--volume", f"{source}:{target}:{mode}"]
    argv += [spec.image, *spec.argv]
    return argv


def scan_for_canary(surface: Iterable[str], canary: str) -> list[str]:
    """Return each surface entry that contains ``canary``, with the value redacted.

    Redaction keeps the leak location auditable without echoing the secret.
    """
    hits: list[str] = []
    for entry in surface:
        if canary in entry:
            hits.append(entry.replace(canary, "..."))
    return hits
