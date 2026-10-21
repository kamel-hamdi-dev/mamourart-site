"""Synthetic HTTP installation regressions, executed against the real worker code."""
import subprocess

import pytest

from tests.checks import ROOT


@pytest.mark.parametrize("scenario", [
    "safe", "no-store", "private", "vary-star", "redirected",
    "http-301", "http-302", "http-307", "http-308", "http-404", "http-500", "http-503",
    "opaque", "cors", "default", "error", "foreign-origin", "wrong-path", "private-result-url", "empty-url", "body-used", "null-body",
    "network", "cache-open", "cache-write", "cleanup-failure", "transition",
    "request-foreign", "request-protocol-relative", "request-php", "request-result", "request-query", "request-fragment",
])
def test_precache_validates_before_storage(scenario):
    result = subprocess.run(
        ["node", str(ROOT / "tests/worker_mission42.cjs"), str(ROOT / "service-worker.js"), scenario],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
