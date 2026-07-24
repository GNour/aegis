"""doctor classifies environment health; repair performs only bounded remediations."""

from aegis.deploy.doctor import REQUIRED_CHECKS, doctor, repair


def _all_ok() -> dict[str, bool]:
    return {name: True for name in REQUIRED_CHECKS}


def test_healthy_environment_passes() -> None:
    report = doctor(_all_ok())
    assert report.ok is True
    assert report.failures() == []


def test_missing_check_is_treated_as_failure() -> None:
    report = doctor({})  # nothing reported healthy
    assert report.ok is False
    assert set(report.failures()) == set(REQUIRED_CHECKS)


def test_broken_check_is_flagged() -> None:
    checks = _all_ok()
    checks["readiness"] = False
    report = doctor(checks)
    assert report.ok is False
    assert "readiness" in report.failures()


def test_repair_fixes_only_bounded_checks() -> None:
    checks = _all_ok()
    checks["permissions"] = False  # remediable
    checks["readiness"] = False  # not remediable
    result = repair(doctor(checks))
    assert "permissions" in result.changed
    assert "readiness" in result.manual
    assert "readiness" not in result.changed
