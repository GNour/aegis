"""Workers receive only their declared skills, digest-verified and read-only."""

from pathlib import Path

import pytest

from aegis.context.skills import SkillRegistry, directory_digest


def _make_skill(root: Path, name: str, body: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")


@pytest.fixture
def registry_root(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    _make_skill(root, "tdd", "# tdd\n")
    _make_skill(root, "backend", "# backend\n")
    _make_skill(root, "deployment", "# deployment\n")
    return root


@pytest.fixture
def skill_registry(registry_root: Path) -> SkillRegistry:
    manifest = {
        "tdd": {
            "version": "1.2.0",
            "path": "tdd",
            "digest": directory_digest(registry_root / "tdd"),
        },
        "backend": {
            "version": "2.0.1",
            "path": "backend",
            "digest": directory_digest(registry_root / "backend"),
        },
        "deployment": {
            "version": "0.1.0",
            "path": "deployment",
            "digest": directory_digest(registry_root / "deployment"),
        },
    }
    return SkillRegistry(registry_root, manifest)


def test_worker_receives_only_declared_skills(skill_registry, tmp_path) -> None:
    bundle = skill_registry.bundle({"tdd": "1.2.0", "backend": "2.0.1"}, tmp_path / "bundle")
    assert sorted(path.name for path in bundle.iterdir()) == ["backend", "tdd"]
    assert not bundle.joinpath("deployment").exists()
    assert bundle.stat().st_mode & 0o222 == 0


def test_unknown_skill_version_fails_closed(skill_registry, tmp_path) -> None:
    with pytest.raises(ValueError, match="unknown skill version"):
        skill_registry.bundle({"tdd": "99.0.0"}, tmp_path / "bundle")


def test_unknown_skill_id_fails_closed(skill_registry, tmp_path) -> None:
    with pytest.raises(ValueError, match="unknown skill version"):
        skill_registry.bundle({"ghost": "1.0.0"}, tmp_path / "bundle")


def test_digest_mismatch_fails_closed(registry_root, tmp_path) -> None:
    manifest = {"tdd": {"version": "1.2.0", "path": "tdd", "digest": "0" * 64}}
    registry = SkillRegistry(registry_root, manifest)
    with pytest.raises(ValueError, match="digest mismatch"):
        registry.bundle({"tdd": "1.2.0"}, tmp_path / "bundle")


def test_path_escaping_registry_fails_closed(registry_root, tmp_path) -> None:
    manifest = {"evil": {"version": "1.0.0", "path": "../../etc", "digest": "0" * 64}}
    registry = SkillRegistry(registry_root, manifest)
    with pytest.raises(ValueError, match="escapes registry"):
        registry.bundle({"evil": "1.0.0"}, tmp_path / "bundle")


def test_bundled_files_are_read_only(skill_registry, tmp_path) -> None:
    bundle = skill_registry.bundle({"tdd": "1.2.0"}, tmp_path / "bundle")
    skill_file = bundle / "tdd" / "SKILL.md"
    assert skill_file.stat().st_mode & 0o222 == 0


def test_digest_map_records_resolved_digests(skill_registry) -> None:
    digests = skill_registry.digest_map({"tdd": "1.2.0", "backend": "2.0.1"})
    assert set(digests) == {"tdd", "backend"}
    assert all(len(value) == 64 for value in digests.values())
