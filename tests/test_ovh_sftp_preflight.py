"""Tests sans reseau du controle prealable OVH (Mission 26)."""
import base64
import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

from tests.checks import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import ovh_sftp_preflight as preflight  # noqa: E402

NAMES = ("index.html", "contact-submit.php", "legal.html", "service-worker.js")


def fake_key():
    label = b"ssh-ed25519"
    return struct.pack(">I", len(label)) + label + struct.pack(">I", 32) + bytes(range(32))


def setup_fake(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    private = tmp_path / "private"
    backup = tmp_path / "backup"
    repo.mkdir()
    private.mkdir()
    backup.mkdir()
    for name in NAMES:
        (repo / name).write_text("fictif")
    (repo / "deploy-manifest.json").write_text(json.dumps({"version": 1, "files": list(NAMES)}))
    raw = fake_key()
    fingerprint = base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
    (private / "known_hosts").write_text(
        preflight.HOST + " ssh-ed25519 " + base64.b64encode(raw).decode() + "\n", encoding="ascii"
    )
    monkeypatch.setattr(preflight, "OBSERVED_SHA256", fingerprint)
    return repo, private, backup


def test_all_valid_offline(tmp_path, monkeypatch):
    repo, private, backup = setup_fake(tmp_path, monkeypatch)
    checks, ok = preflight.perform_checks(repo, private, backup, disk_free=40 * 1024 * 1024)
    assert ok and len(checks) == 5
    assert all(x[1] for x in checks)


def test_missing_known_hosts_blocks(tmp_path, monkeypatch):
    repo, private, backup = setup_fake(tmp_path, monkeypatch)
    (private / "known_hosts").unlink()
    _, ok = preflight.perform_checks(repo, private, backup, disk_free=40 * 1024 * 1024)
    assert not ok


def test_mismatched_fingerprint_blocks(tmp_path, monkeypatch):
    repo, private, backup = setup_fake(tmp_path, monkeypatch)
    monkeypatch.setattr(preflight, "OBSERVED_SHA256", "invalide")
    checks, ok = preflight.perform_checks(repo, private, backup, disk_free=40 * 1024 * 1024)
    assert not ok and any("empreinte differente" in msg for _, valid, msg in checks if not valid)


def test_unknown_host_or_key_type_blocks(tmp_path, monkeypatch):
    _, private, _ = setup_fake(tmp_path, monkeypatch)
    path = private / "known_hosts"
    original = path.read_text()
    path.write_text(original.replace(preflight.HOST, "other.invalid"))
    with pytest.raises(ValueError, match="serveur"):
        preflight.fingerprint_from_known_hosts(path)
    path.write_text(original.replace("ssh-ed25519", "ssh-rsa", 1))
    with pytest.raises(ValueError, match="type"):
        preflight.fingerprint_from_known_hosts(path)


def test_corrupted_key_blocks(tmp_path, monkeypatch):
    _, private, _ = setup_fake(tmp_path, monkeypatch)
    path = private / "known_hosts"
    path.write_text(preflight.HOST + " ssh-ed25519 !!!\n")
    with pytest.raises(ValueError, match="Base64"):
        preflight.fingerprint_from_known_hosts(path)


def test_missing_manifest_file_blocks(tmp_path, monkeypatch):
    repo, private, backup = setup_fake(tmp_path, monkeypatch)
    (repo / "index.html").unlink()
    _, ok = preflight.perform_checks(repo, private, backup, disk_free=40 * 1024 * 1024)
    assert not ok


def test_backup_in_repo_blocks(tmp_path, monkeypatch):
    repo, private, _ = setup_fake(tmp_path, monkeypatch)
    internal = repo / "backup"
    internal.mkdir()
    checks, ok = preflight.perform_checks(repo, private, internal, disk_free=40 * 1024 * 1024)
    assert not ok and any("distinct" in msg for _, valid, msg in checks if not valid)


def test_backup_in_cloud_path_blocks(tmp_path, monkeypatch):
    repo, private, _ = setup_fake(tmp_path, monkeypatch)
    cloud = tmp_path / "OneDrive" / "backup"
    cloud.mkdir(parents=True)
    _, ok = preflight.perform_checks(repo, private, cloud, disk_free=40 * 1024 * 1024)
    assert not ok


def test_insufficient_space_blocks(tmp_path, monkeypatch):
    repo, private, backup = setup_fake(tmp_path, monkeypatch)
    _, ok = preflight.perform_checks(repo, private, backup, disk_free=100)
    assert not ok


def test_cli_is_read_only_and_no_secrets(tmp_path, monkeypatch, capsys):
    repo, private, backup = setup_fake(tmp_path, monkeypatch)
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _: type("D", (), {"free": 40 * 1024 * 1024})())
    original = {p: p.read_bytes() for folder in (repo, private) for p in folder.iterdir() if p.is_file()}
    assert preflight.main(["--repo", str(repo), "--private-dir", str(private), "--backup-dir", str(backup)]) == 0
    out = capsys.readouterr().out
    assert "aucun acces OVH" in out and "aucun secret lu" in out
    assert "non certifiee independamment" in out
    assert not list(backup.iterdir())
    assert all(p.read_bytes() == data for p, data in original.items())
