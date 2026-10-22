"""Synthetic HTTP installation regressions, executed against the real worker code."""
import subprocess

import pytest

from tests.checks import ROOT


@pytest.mark.parametrize("scenario", [
    "safe", "activation-corruption", "stored-corruption", "png-variant", "no-store", "private", "vary-star", "redirected",
    "http-301", "http-302", "http-307", "http-308", "http-404", "http-500", "http-503",
    "opaque", "cors", "default", "error", "foreign-origin", "wrong-path", "private-result-url", "empty-url", "body-used", "null-body",
    "network", "cache-open", "cache-write", "cleanup-failure", "transition",
    "empty-body", "wrong-mime", "missing-mime", "invalid-html", "invalid-utf8", "oversized-body",
    "read-error", "truncated-stream", "invalid-json", "invalid-manifest", "invalid-image", "truncated-image", "image-wrong-mime", "image-wrong-encoding", "cleanup-total-failure",
    "request-foreign", "request-protocol-relative", "request-php", "request-result", "request-query", "request-fragment",
])
def test_precache_validates_before_storage(scenario):
    result = subprocess.run(
        ["node", str(ROOT / "tests/worker_mission42.cjs"), str(ROOT / "service-worker.js"), scenario],
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS service worker {scenario}" in result.stdout, "The async scenario must complete, not merely exit Node"
