"""Immutable resource identity and port leasing for task-scoped services.

Every rootless resource a task owns carries the same immutable label/nonce set.
Cleanup and reconciliation match on this exact identity, so the control plane never
touches another task's — or an operator's — containers, networks, or volumes.
"""

from dataclasses import dataclass, field
from threading import Lock


@dataclass(frozen=True)
class ResourceIdentity:
    instance: str
    task_id: str
    nonce: str

    def labels(self) -> dict[str, str]:
        return {
            "dev.aegis.instance": self.instance,
            "dev.aegis.task": self.task_id,
            "dev.aegis.nonce": self.nonce,
            "dev.aegis.managed": "true",
        }

    def label_selectors(self) -> list[str]:
        """Docker ``--filter label=k=v`` selectors matching this exact identity."""
        return [f"label={key}={value}" for key, value in self.labels().items()]

    @property
    def compose_project(self) -> str:
        return f"aegis_{self.task_id.replace('-', '')[:16]}_{self.nonce[:8]}"


@dataclass
class PortAllocator:
    """Leases host ports from a bounded range, released per task.

    Deterministic and in-process: production reconciliation persists leases in the
    state store, but the allocation policy — first free port in range, released as a
    set per task — lives here so it can be tested without a database.
    """

    start: int
    end: int
    _leases: dict[str, dict[str, int]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def _in_use(self) -> set[int]:
        return {port for ports in self._leases.values() for port in ports.values()}

    def allocate(self, task_id: str, service: str) -> int:
        with self._lock:
            in_use = self._in_use()
            for port in range(self.start, self.end + 1):
                if port not in in_use:
                    self._leases.setdefault(task_id, {})[service] = port
                    return port
            raise RuntimeError("no free ports in range")

    def release(self, task_id: str) -> None:
        with self._lock:
            self._leases.pop(task_id, None)

    def leases_for(self, task_id: str) -> dict[str, int]:
        return dict(self._leases.get(task_id, {}))
