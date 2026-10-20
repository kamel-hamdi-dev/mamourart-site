"""Mission 26 : garde-fous pour la simulation OVH (aucun reseau)."""
import importlib.util
import json
from pathlib import Path

import pytest

from tests.checks import ROOT

SOURCE = ROOT / "scripts" / "ovh_deploy_plan.py"
spec = importlib.util.spec_from_file_location("ovh_deploy_plan", SOURCE)
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)

PUBLIC_FILES = ("index.html", "contact-submit.php", "contact-rate-limit.php", "legal.html", "service-worker.js")


def write_manifest(root, names):
    (root / "deploy-manifest.json").write_text(json.dumps({"version": 1, "files": list(names)}), encoding="utf-8")


@pytest.fixture
def public_repo(tmp_path):
    for name in PUBLIC_FILES:
        (tmp_path / name).write_text("public fixture: " + name, encoding="utf-8")
    write_manifest(tmp_path, PUBLIC_FILES)
    return tmp_path


def test_plan_contains_only_explicit_public_files():
    rows = plan.build_plan(ROOT)
    names = [row["file"] for row in rows]
    assert "index.html" in names
    assert "contact-submit.php" in names
    assert "contact-rate-limit.php" in names
    assert {name for name in names if name.endswith(".php")} == {"contact-submit.php", "contact-rate-limit.php"}
    assert "legal.html" in names
    assert "service-worker.js" in names
    assert len(names) == len(set(names))
    assert ".github" not in names
    assert ".env" not in names
    assert all(len(row["sha256"]) == 64 and row["bytes"] > 0 for row in rows)


@pytest.mark.parametrize("invalid", ["../secret.txt", "private/.env", ".env", ".htpasswd", "test.py", "\\attack.html", "private-key.pem"])
def test_plan_rejects_traversal_and_hidden_paths(public_repo, invalid):
    write_manifest(public_repo, [*PUBLIC_FILES, invalid])
    with pytest.raises(ValueError, match="Nom non autorise"):
        plan.build_plan(public_repo)


@pytest.mark.parametrize("missing", ["contact-submit.php", "contact-rate-limit.php"])
def test_plan_rejects_either_php_dependency_missing_from_manifest(public_repo, missing):
    write_manifest(public_repo, [name for name in PUBLIC_FILES if name != missing])
    with pytest.raises(ValueError, match="indispensables manquants: " + missing):
        plan.build_plan(public_repo)


@pytest.mark.parametrize("missing", ["index.html", "contact-submit.php", "contact-rate-limit.php"])
def test_plan_rejects_missing_files(public_repo, missing):
    (public_repo / missing).unlink()
    with pytest.raises(ValueError, match="absent"):
        plan.build_plan(public_repo)


@pytest.mark.parametrize("name", ["contact-submit.php", "contact-rate-limit.php"])
def test_plan_rejects_symlinked_php_dependency(public_repo, tmp_path, name):
    target = tmp_path / "other-public-fixture.txt"
    target.write_text("not the dependency", encoding="utf-8")
    (public_repo / name).unlink()
    (public_repo / name).symlink_to(target)
    with pytest.raises(ValueError, match="lien symbolique interdit"):
        plan.build_plan(public_repo)


def test_plan_validation_remains_read_only(public_repo):
    original = {path.name: path.read_bytes() for path in public_repo.iterdir()}
    rows = plan.build_plan(public_repo)
    assert {row["file"] for row in rows} == set(PUBLIC_FILES)
    assert {path.name: path.read_bytes() for path in public_repo.iterdir()} == original


def test_simulation_workflow_is_manual_and_has_no_ovh_access():
    content = (ROOT / ".github/workflows/ovh-deploy-plan.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in content
    assert "pull_request:" not in content and "push:" not in content
    assert "secrets." not in content
    assert "contents: read" in content
    assert "scripts/ovh_deploy_plan.py" in content
    assert "python -m pytest" in content
    assert "php -l contact-submit.php" in content
    assert "sftp " not in content.lower() and "rsync " not in content.lower()
