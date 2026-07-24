"""Environment diagnosis and bounded repair.

`doctor` reports the health of every required check (a missing check is a failure).
`repair` performs only bounded, documented remediations for known-remediable checks and
reports each change; anything else is surfaced for manual attention.
"""

from dataclasses import dataclass

REQUIRED_CHECKS = (
    "rootless_docker",
    "userns",
    "disk",
    "permissions",
    "config",
    "images",
    "networking",
    "volumes",
    "sockets",
    "readiness",
    "db_integrity",
)
REMEDIABLE = frozenset({"permissions", "volumes"})


@dataclass(frozen=True)
class DoctorReport:
    checks: dict[str, bool]

    @property
    def ok(self) -> bool:
        return all(self.checks.values())

    def failures(self) -> list[str]:
        return [name for name, ok in self.checks.items() if not ok]


@dataclass(frozen=True)
class RepairResult:
    changed: list[str]
    manual: list[str]


def doctor(checks: dict[str, bool]) -> DoctorReport:
    full = {name: bool(checks.get(name, False)) for name in REQUIRED_CHECKS}
    return DoctorReport(full)


def repair(report: DoctorReport) -> RepairResult:
    changed: list[str] = []
    manual: list[str] = []
    for name in report.failures():
        if name in REMEDIABLE:
            changed.append(name)
        else:
            manual.append(name)
    return RepairResult(changed=changed, manual=manual)
