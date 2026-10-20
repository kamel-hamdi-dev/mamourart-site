"""Mission 26 phase 2: strictly offline SFTP snapshot and rollback tests."""
import io
import json
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.checks import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import ovh_sftp_snapshot as snapshot  # noqa: E402

NAMES = ("index.html", "contact-submit.php", "contact-rate-limit.php", "legal.html", "service-worker.js")


class ReadOnlyFakeSFTP:
    def __init__(self, content, mode=stat.S_IFREG | 0o644):
        self.content = content
        self.mode = mode
        self.reads = []

    def lstat(self, remote):
        self.reads.append(("lstat", remote))
        return SimpleNamespace(st_mode=self.mode, st_size=len(self.content[Path(remote).name]))

    def open(self, remote, mode):
        assert mode == "rb", "Remote SFTP must remain read-only"
        self.reads.append(("open", remote))
        return io.BytesIO(self.content[Path(remote).name])

    def put(self, *_):
        raise AssertionError("Remote write is forbidden")

    def remove(self, *_):
        raise AssertionError("Remote deletion is forbidden")


def fixture_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    content = {name: ("mamourart-test:" + name).encode() for name in NAMES}
    for name, data in content.items():
        (repo / name).write_bytes(data)
    (repo / "deploy-manifest.json").write_text(json.dumps({"version": 1, "files": list(NAMES)}), encoding="utf-8")
    return repo, content


def test_backup_copies_allowed_files_and_verifies_hashes(tmp_path):
    repo, content = fixture_repo(tmp_path)
    sftp = ReadOnlyFakeSFTP(content)
    dest = tmp_path / "private-snapshot"
    receipt = snapshot.backup_from_sftp(sftp, repo, dest)
    assert len(receipt["files"]) == len(NAMES)
    assert snapshot.verify_snapshot(dest) == receipt
    assert {p.name for p in dest.iterdir()} == set(NAMES) | {"backup-receipt.json"}
    assert all(mode.startswith("/") and mode.startswith(snapshot.REMOTE_BASE) for op, mode in sftp.reads)
    assert len(sftp.reads) == 2 * len(NAMES)


def test_rollback_is_print_only_and_does_not_modify_snapshot(tmp_path):
    repo, content = fixture_repo(tmp_path)
    dest = tmp_path / "snapshot"
    snapshot.backup_from_sftp(ReadOnlyFakeSFTP(content), repo, dest)
    original = {p.name: snapshot.file_hash(p) for p in dest.iterdir()}
    plan = snapshot.rollback_plan(dest)
    assert "AUCUNE RESTAURATION" in plan
    assert "NON IMPLEMENTEE" in plan
    assert {p.name: snapshot.file_hash(p) for p in dest.iterdir()} == original


def test_tampered_backup_is_rejected(tmp_path):
    repo, content = fixture_repo(tmp_path)
    dest = tmp_path / "snapshot"
    snapshot.backup_from_sftp(ReadOnlyFakeSFTP(content), repo, dest)
    (dest / "index.html").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="Empreinte ou taille incorrecte"):
        snapshot.verify_snapshot(dest)


def test_symlink_or_nonregular_remote_is_rejected(tmp_path):
    repo, content = fixture_repo(tmp_path)
    dest = tmp_path / "snapshot"
    with pytest.raises(ValueError, match="lien symbolique"):
        snapshot.backup_from_sftp(ReadOnlyFakeSFTP(content, stat.S_IFLNK | 0o777), repo, dest)
    assert (dest / "INCOMPLETE.txt").is_file()
    with pytest.raises(ValueError, match="incomplete"):
        snapshot.verify_snapshot(dest)


def test_incomplete_download_is_rejected(tmp_path):
    repo, content = fixture_repo(tmp_path)
    class BadSize(ReadOnlyFakeSFTP):
        def lstat(self, remote):
            result = super().lstat(remote)
            result.st_size += 1
            return result
    dest = tmp_path / "snapshot"
    with pytest.raises(ValueError, match="incomplete"):
        snapshot.backup_from_sftp(BadSize(content), repo, dest)
    assert (dest / "INCOMPLETE.txt").is_file()


def test_rejects_wrong_remote_directory_and_repository_destination(tmp_path):
    repo, content = fixture_repo(tmp_path)
    sftp = ReadOnlyFakeSFTP(content)
    with pytest.raises(ValueError, match="non approuve"):
        snapshot.backup_from_sftp(sftp, repo, tmp_path / "backup", remote_base="/tmp/site")
    with pytest.raises(ValueError, match="depot Git"):
        snapshot.backup_from_sftp(sftp, repo, repo / "backup")
    assert sftp.reads == []


def test_missing_or_unexpected_backup_file_is_rejected(tmp_path):
    repo, content = fixture_repo(tmp_path)
    dest = tmp_path / "snapshot"
    snapshot.backup_from_sftp(ReadOnlyFakeSFTP(content), repo, dest)
    (dest / "unexpected.txt").write_text("unexpected")
    with pytest.raises(ValueError, match="supplementaires"):
        snapshot.verify_snapshot(dest)


def test_demo_has_no_server_credentials_or_network_dependency():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ovh_sftp_snapshot.py"), "--demo"],
        text=True, capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "Aucune connexion OVH" in result.stdout
    assert "aucune modification distante" in result.stdout


def test_existing_github_workflow_remains_simulation_only():
    workflow = (ROOT / ".github/workflows/ovh-deploy-plan.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "secrets." not in workflow
    assert "ovh_sftp_snapshot" not in workflow
    assert "aucun deploiement" in workflow.lower()
