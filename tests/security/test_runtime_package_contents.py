"""The built wheel must embed the compiled catalog but no companion source or installer."""

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UV = shutil.which("uv")


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory) -> Path:
    if UV is None:
        pytest.skip("uv not available to build the wheel")
    out = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        [UV, "build", "--wheel", "--out-dir", str(out)],
        check=True,
        cwd=ROOT,
        capture_output=True,
    )
    wheels = list(out.glob("*.whl"))
    assert wheels, "no wheel produced"
    return wheels[0]


def test_wheel_contains_compiled_catalog_but_not_subagents_source(built_wheel: Path) -> None:
    with zipfile.ZipFile(built_wheel) as wheel:
        names = set(wheel.namelist())
    assert "aegis/data/companions/roles.compiled.json" in names
    assert "aegis/data/companions/roles.provenance.json" in names
    assert all("packages/subagents" not in name for name in names)
    assert all("packages/promptx" not in name for name in names)
    assert all(not name.endswith("install.sh") for name in names)
    assert all("node_modules" not in name for name in names)
