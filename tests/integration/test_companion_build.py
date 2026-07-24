"""The companion build/check commands must pass on the committed, pinned sources."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "companions.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args], cwd=ROOT, capture_output=True, text=True
    )


def test_verify_sources_passes() -> None:
    result = run("verify-sources")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_compiled_assets_are_up_to_date() -> None:
    result = run("compile-subagents", "--check")
    assert result.returncode == 0, result.stderr
