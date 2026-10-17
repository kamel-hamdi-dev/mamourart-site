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


def test_plan_contains_only_explicit_public_files():
    rows = plan.build_plan(ROOT)
    names = [row["file"] for row in rows]
    assert "index.html" in names
    assert "contact-submit.php" in names
    assert "legal.html" in names
    assert "service-worker.js" in names
    assert len(names) == len(set(names))
    assert ".github" not in names
    assert ".env" not in names
    assert all(len(row["sha256"]) == 64 and row["bytes"] > 0 for row in rows)


def test_plan_rejects_traversal_and_hidden_paths(tmp_path):
    for invalid in ["../secret.txt", "private/.env", ".htpasswd", "test.py", "\\attack.html"]:
        (tmp_path / "deploy-manifest.json").write_text(json.dumps({"version": 1, "files":
            ["index.html", "contact-submit.php", "legal.html", "service-worker.js", invalid]}))
        with pytest.raises(ValueError):
            plan.build_plan(tmp_path)


def test_plan_rejects_missing_files(tmp_path):
    (tmp_path / "deploy-manifest.json").write_text(json.dumps({"version": 1, "files":
        ["index.html", "contact-submit.php", "legal.html", "service-worker.js"]}))
    with pytest.raises(ValueError, match="absent"):
        plan.build_plan(tmp_path)


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
