"""Tests SFTP durcissement : aucun secret reel et aucun reseau."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from tests.checks import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import ovh_sftp_snapshot as snapshot  # noqa: E402
import ovh_sftp_preflight as preflight  # noqa: E402


@pytest.fixture
def cfg(monkeypatch, tmp_path):
    private = tmp_path / "private"
    private.mkdir()
    known = private / "known_hosts"
    known.write_text("TEST ONLY")
    monkeypatch.setattr(snapshot, "_private_dir", lambda: private)
    monkeypatch.setenv("OVH_SFTP_HOST", preflight.HOST)
    monkeypatch.setenv("OVH_SFTP_USER", snapshot.APPROVED_USER)
    monkeypatch.setenv("OVH_SFTP_PORT", "22")
    monkeypatch.setenv("OVH_SFTP_KNOWN_HOSTS", str(known))
    monkeypatch.setenv("OVH_SFTP_AUTH", "password")
    monkeypatch.setenv("OVH_SFTP_PASSWORD", "test-only-secret")
    monkeypatch.delenv("OVH_SFTP_KEY_FILE", raising=False)
    return private


def test_host_is_pinned(cfg, monkeypatch):
    monkeypatch.setenv("OVH_SFTP_HOST", "untrusted.invalid")
    with pytest.raises(RuntimeError, match="Hote"):
        snapshot._sftp_connection_config()


def test_user_is_pinned(cfg, monkeypatch):
    monkeypatch.setenv("OVH_SFTP_USER", "unknown")
    with pytest.raises(RuntimeError, match="utilisateur"):
        snapshot._sftp_connection_config()


def test_port_is_pinned(cfg, monkeypatch):
    monkeypatch.setenv("OVH_SFTP_PORT", "2222")
    with pytest.raises(RuntimeError, match="port 22"):
        snapshot._sftp_connection_config()


def test_wrong_known_hosts_path_blocks(cfg, monkeypatch, tmp_path):
    other = tmp_path / "other_known_hosts"
    other.write_text("TEST")
    monkeypatch.setenv("OVH_SFTP_KNOWN_HOSTS", str(other))
    with pytest.raises(RuntimeError, match="known_hosts"):
        snapshot._sftp_connection_config()


def test_safe_backup_target_accepts_only_new_direct_snapshot(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    root = tmp_path / "backup"
    root.mkdir()
    monkeypatch.setattr(snapshot, "_backup_root", lambda: root)
    assert snapshot._safe_backup_target(repo, root / "snapshot-2026-10-19") == root


def test_destination_outside_private_root_blocks(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    root = tmp_path / "backup"
    root.mkdir()
    monkeypatch.setattr(snapshot, "_backup_root", lambda: root)
    with pytest.raises(RuntimeError, match="uniquement"):
        snapshot._safe_backup_target(repo, tmp_path / "outside" / "snapshot-2026-10-19")


def test_existing_destination_blocks(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    root = tmp_path / "backup"
    root.mkdir()
    target = root / "snapshot-existing"
    target.mkdir()
    monkeypatch.setattr(snapshot, "_backup_root", lambda: root)
    with pytest.raises(RuntimeError, match="existe"):
        snapshot._safe_backup_target(repo, target)


def test_invalid_snapshot_name_blocks(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    root = tmp_path / "backup"
    root.mkdir()
    monkeypatch.setattr(snapshot, "_backup_root", lambda: root)
    with pytest.raises(RuntimeError, match="Nom"):
        snapshot._safe_backup_target(repo, root / "website")


def test_preflight_failure_blocks_before_auth_or_network(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    root = tmp_path / "backup"
    root.mkdir()
    monkeypatch.setattr(snapshot, "_backup_root", lambda: root)
    monkeypatch.setattr(snapshot, "_private_dir", lambda: tmp_path / "private")
    monkeypatch.setattr(snapshot.preflight, "perform_checks", lambda *_: (
        [("empreinte SSH", False, "cle inconnue")], False))
    def no_credentials():
        raise AssertionError("Mot de passe ne doit pas etre consulte")
    monkeypatch.setattr(snapshot, "_sftp_connection_config", no_credentials)
    with pytest.raises(RuntimeError, match="Preflight obligatoire"):
        snapshot._backup_readonly(repo, root / "snapshot-demo")


def test_preflight_rejects_symlink_directories(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    private = tmp_path / "private"
    backup = tmp_path / "backup"
    private.mkdir()
    backup.mkdir()
    sym = tmp_path / "redirect"
    try:
        sym.symlink_to(backup, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Creation de symlink non autorisee dans cet environnement")
    checks, ok = preflight.perform_checks(repo, private, sym, disk_free=30 * 1024 * 1024)
    assert not ok
    assert any(name == "Dossier de sauvegardes" and not valid for name, valid, _ in checks)


def test_preflight_success_checks_before_password(cfg, monkeypatch, tmp_path):
    root = tmp_path / "backup"
    root.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(snapshot, "_backup_root", lambda: root)
    verified = []
    monkeypatch.setattr(snapshot.preflight, "perform_checks", lambda *_: (verified.append(True) or [], True))
    fake = SimpleNamespace(
        SSHClient=lambda: FakeSSH(),
        RejectPolicy=lambda: object(),
    )
    class FakeSFTP:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    class FakeSSH:
        def load_host_keys(self, *_):
            assert verified
        def set_missing_host_key_policy(self, *_):
            pass
        def connect(self, **kwargs):
            assert verified and kwargs["hostname"] == preflight.HOST
        def open_sftp(self):
            return FakeSFTP()
        def close(self):
            pass
    monkeypatch.setitem(sys.modules, "paramiko", fake)
    monkeypatch.setattr(snapshot, "backup_from_sftp", lambda *_: {"files": [{"file": "fictif"}]})
    snapshot._backup_readonly(repo, root / "snapshot-demo")
    assert verified
