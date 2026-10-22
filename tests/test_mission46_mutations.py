"""Prove negative scenarios reject their intended defect, not arbitrary errors."""
import subprocess

import pytest

from tests.checks import ROOT


def run(worker, scenario, harness=None):
    return subprocess.run(
        ['node', str(harness or ROOT / 'tests/worker_mission42.cjs'), str(worker), scenario],
        capture_output=True, text=True, timeout=20,
    )


def test_old_negative_assertion_accepts_unrelated_failure(tmp_path):
    baseline = (ROOT / 'tests/worker_mission42.cjs').read_text()
    strict_assertion = """await assert.rejects(lifecycle('install'), error => {
    assert.match(error.message, expectedError, scenario + ' must fail for its intended cause');
    return true;
  });"""
    assert strict_assertion in baseline
    baseline = baseline.replace(strict_assertion,
        "await assert.rejects(lifecycle('install'), undefined, scenario + ' must abort installation');")
    # Keep the fixture root independent of the temporary harness location.
    baseline = baseline.replace("path.resolve(__dirname, '..')", repr(str(ROOT)))
    harness = tmp_path / 'old.cjs'
    harness.write_text(baseline)
    worker = tmp_path / 'unrelated.js'
    worker.write_text((ROOT / 'service-worker.js').read_text().replace(
        'async function installPrecache() {',
        'async function installPrecache() { throw new Error("unrelated sentinel failure");',
    ))
    old = run(worker, 'empty-body', harness)
    assert old.returncode == 0 and 'PASS service worker empty-body' in old.stdout
    fixed = run(worker, 'empty-body')
    assert fixed.returncode != 0
    assert 'intended cause' in fixed.stderr


@pytest.mark.parametrize(('before', 'after', 'scenario'), [
    ('if (!await hasValidContent(response, url)) {', 'if (false) {', 'empty-body'),
    ('if (!await hasValidContent(response, url)) {', 'if (false) {', 'read-error'),
    ('cache = await caches.open(CACHE_NAME);', 'cache = null;', 'cache-open'),
    ('for (const [url, response] of candidates) await cache.put(url, response);', '', 'cache-write'),
    ('    await verifyCandidate(cache);', '', 'stored-corruption'),
    ('    await verifyCandidate(await caches.open(CACHE_NAME));', '', 'cleanup-total-failure'),
    ('for (const request of await cache.keys()) await cache.delete(request);', '', 'cleanup-total-failure'),
])
def test_harness_kills_defective_workers(tmp_path, before, after, scenario):
    source = (ROOT / 'service-worker.js').read_text()
    assert before in source
    worker = tmp_path / 'mutant.js'
    worker.write_text(source.replace(before, after, 1))
    result = run(worker, scenario)
    assert result.returncode != 0, result.stdout + result.stderr
    assert 'PASS service worker ' not in result.stdout
