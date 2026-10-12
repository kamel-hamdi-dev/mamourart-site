import re
import shutil
import subprocess

import pytest

from tests.checks import ROOT, png_size, read_text, site_file

EVENTS = ("install", "activate", "fetch")


def source() -> str:
    return read_text("service-worker.js")


def precache_entries() -> list[str]:
    match = re.search(r"FILES_TO_CACHE\s*=\s*\[(.*?)\]", source(), re.S)
    assert match, "FILES_TO_CACHE is missing"
    return re.findall(r"""['"]([^'"]+)['"]""", match.group(1))


def test_service_worker_javascript_parses():
    node = shutil.which("node")
    if node is None:
        pytest.fail("node is required to syntax-check service-worker.js")
    result = subprocess.run(
        [node, "--check", str(ROOT / "service-worker.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_cache_name_and_precache_files():
    worker = source()
    name = re.search(r"""CACHE_NAME\s*=\s*['"]([^'"]+)['"]""", worker)
    assert name, "CACHE_NAME is missing"
    assert re.fullmatch(r"mamourart-v\d+", name.group(1))

    entries = precache_entries()
    assert entries
    assert len(entries) == len(set(entries))
    assert "/" in entries
    for entry in entries:
        assert entry.startswith("/"), entry
        path = site_file(entry)
        assert path.is_file(), entry
        if path.suffix.lower() == ".png":
            png_size(path)


def test_service_worker_handles_install_activate_and_fetch():
    worker = source()
    for event in EVENTS:
        assert re.search(rf"""addEventListener\(\s*['"]{event}['"]""", worker), event
    assert "cache.addAll" in worker
    assert "caches.delete" in worker
    assert "skipWaiting" in worker
    assert "clients.claim" in worker
    assert re.search(r"""request\.method\s*!==\s*['"]GET['"]""", worker)
