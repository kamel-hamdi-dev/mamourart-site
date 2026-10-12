"""The required GitHub check stays free of public-network tests."""

import os
import subprocess
import sys

from tests.checks import ROOT

WORKFLOW = ROOT / ".github" / "workflows" / "site-checks.yml"


def test_required_check_name_and_external_split():
    text = WORKFLOW.read_text(encoding="utf-8")
    required, external = text.split("\n  external-links:\n", 1)

    assert required.count("name: Python site checks") == 1
    assert "name: Python site checks" not in external
    assert '-m "not external"' in required
    assert "--ignore=tests/test_external_links.py" in required
    assert "--mode required" in required
    assert "continue-on-error:" not in required

    assert "name: External link checks" in external
    assert "-m external" in external
    assert "--mode optional" in external
    assert "continue-on-error: true" in external


def test_required_selection_excludes_external_links():
    result = _collect("not external")
    assert result.returncode == 0, result.stderr
    assert "test_external_links_respond" not in result.stdout
    assert "test_homepage_document" in result.stdout


def test_external_selection_is_only_the_network_check():
    result = _collect("external")
    assert result.returncode == 0, result.stderr
    collected = [line for line in result.stdout.splitlines() if "::" in line]
    assert collected == ["tests/test_external_links.py::test_external_links_respond"]


def test_external_module_is_marked():
    import tests.test_external_links as external

    marks = external.pytestmark if isinstance(external.pytestmark, list) else [external.pytestmark]
    assert any(mark.name == "external" for mark in marks)


def _collect(marker: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTEST_CURRENT_TEST", None)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            marker,
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
