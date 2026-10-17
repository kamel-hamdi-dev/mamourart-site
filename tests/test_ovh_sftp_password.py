"""Mission 26 : authentification SFTP password/key, tests strictement hors ligne."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.checks import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import ovh_sftp_snapshot as snapshot  # noqa: E402


@pytest.fixture
def valid_config(monkeypatch, tmp_path):
    for item in ("OVH_SFTP_HOST", "OVH_SFTP_USER", "OVH_SFTP_PORT",
                 "OVH_SFTP_KNOWN_HOSTS", "OVH_SFTP_AUTH", "OVH_SFTP_PASSWORD",
                 "OVH_SFTP_KEY_FILE"):
        monkeypatch.delenv(item, raising=False)
    known = tmp_path / "known_hosts"
    known.write_text("test-placeholder-not-used-for-a-connection", encoding="utf-8")
    monkeypatch.setenv("OVH_SFTP_HOST", "fictional-sftp.invalid")
    monkeypatch.setenv("OVH_SFTP_USER", "test-only")
    monkeypatch.setenv("OVH_SFTP_KNOWN_HOSTS", str(known))
    return tmp_path


def test_password_mode_is_explicit_and_preserves_spaces(valid_config, monkeypatch):
    monkeypatch.setenv("OVH_SFTP_AUTH", "password")
    monkeypatch.setenv("OVH_SFTP_PASSWORD", "  secret-fictif  ")
    path, config = snapshot._sftp_connection_config()
    assert path.is_file()
    assert config["password"] == "  secret-fictif  "
    assert "key_filename" not in config
    assert config["port"] == 22
    assert config["look_for_keys"] is False and config["allow_agent"] is False


def test_password_mode_rejects_missing_secret(valid_config, monkeypatch):
    monkeypatch.setenv("OVH_SFTP_AUTH", "password")
    with pytest.raises(RuntimeError, match="OVH_SFTP_PASSWORD"):
        snapshot._sftp_connection_config()
    monkeypatch.setenv("OVH_SFTP_PASSWORD", "   ")
    with pytest.raises(RuntimeError, match="OVH_SFTP_PASSWORD"):
        snapshot._sftp_connection_config()


def test_password_mode_rejects_simultaneous_ssh_key(valid_config, monkeypatch):
    monkeypatch.setenv("OVH_SFTP_AUTH", "password")
    monkeypatch.setenv("OVH_SFTP_PASSWORD", "faux-secret")
    monkeypatch.setenv("OVH_SFTP_KEY_FILE", "fake-private-key")
    with pytest.raises(RuntimeError, match="ambigue"):
        snapshot._sftp_connection_config()


def test_key_mode_remains_supported(valid_config, monkeypatch):
    key = valid_config / "fake-key"
    key.write_text("NOT AN ACTUAL PRIVATE KEY", encoding="utf-8")
    monkeypatch.setenv("OVH_SFTP_KEY_FILE", str(key))
    _, config = snapshot._sftp_connection_config()
    assert config["key_filename"] == str(key)
    assert "password" not in config


def test_key_mode_rejects_password(valid_config, monkeypatch):
    key = valid_config / "fake-key"
    key.write_text("FAKE", encoding="utf-8")
    monkeypatch.setenv("OVH_SFTP_KEY_FILE", str(key))
    monkeypatch.setenv("OVH_SFTP_PASSWORD", "fake-secret")
    with pytest.raises(RuntimeError, match="ambigue"):
        snapshot._sftp_connection_config()


def test_unknown_mode_or_bad_port_refused(valid_config, monkeypatch):
    monkeypatch.setenv("OVH_SFTP_AUTH", "password")
    monkeypatch.setenv("OVH_SFTP_PASSWORD", "fake")
    monkeypatch.setenv("OVH_SFTP_PORT", "99999")
    with pytest.raises(RuntimeError, match="Port SFTP invalide"):
        snapshot._sftp_connection_config()
    monkeypatch.setenv("OVH_SFTP_PORT", "22")
    monkeypatch.setenv("OVH_SFTP_AUTH", "auto")
    with pytest.raises(RuntimeError, match="OVH_SFTP_AUTH"):
        snapshot._sftp_connection_config()


def test_missing_known_hosts_refused(valid_config, monkeypatch):
    monkeypatch.setenv("OVH_SFTP_AUTH", "password")
    monkeypatch.setenv("OVH_SFTP_PASSWORD", "fake")
    monkeypatch.setenv("OVH_SFTP_KNOWN_HOSTS", str(valid_config / "missing"))
    with pytest.raises(RuntimeError, match="known_hosts"):
        snapshot._sftp_connection_config()


def test_connection_uses_reject_policy_no_network(valid_config, monkeypatch):
    monkeypatch.setenv("OVH_SFTP_AUTH", "password")
    monkeypatch.setenv("OVH_SFTP_PASSWORD", "secret-simulacre")
    calls = []
    sentinel = object()
    class FakeSFTP:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    class FakeClient:
        def load_host_keys(self, path):
            calls.append(("known_hosts", path))
        def set_missing_host_key_policy(self, policy):
            assert policy is sentinel
            calls.append(("strict_policy", True))
        def connect(self, **kwargs):
            calls.append(("connect_fake", kwargs))
        def open_sftp(self):
            return FakeSFTP()
        def close(self):
            calls.append(("closed", True))
    fake_module = SimpleNamespace(SSHClient=FakeClient, RejectPolicy=lambda: sentinel)
    monkeypatch.setitem(sys.modules, "paramiko", fake_module)
    monkeypatch.setattr(snapshot, "backup_from_sftp", lambda *_: {"files": [{"file": "fictional"}]})
    snapshot._backup_readonly(valid_config / "fake-repo", valid_config / "fake-private-backup")
    assert [action for action, _ in calls] == ["known_hosts", "strict_policy", "connect_fake", "closed"]
    assert calls[2][1]["password"] == "secret-simulacre"
    assert calls[2][1]["hostname"] == "fictional-sftp.invalid"
    assert not (valid_config / "fake-private-backup").exists()


def test_existing_workflow_stays_offline_without_secrets():
    workflow = (ROOT / ".github/workflows/ovh-deploy-plan.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "ovh_sftp_snapshot.py" not in workflow
    assert "secrets." not in workflow
    assert "sftp " not in workflow.lower()
