"""Mission 26: simulation du GO / NO-GO sans reseau ni secret."""
import importlib.util
import subprocess
import sys
from pathlib import Path

from tests.checks import ROOT

SOURCE = ROOT / "scripts/ovh_release_gate.py"
spec = importlib.util.spec_from_file_location("ovh_release_gate", SOURCE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_go_explicite_seulement_pour_main():
    ok, msg = gate.evaluate("GO", gate.EXPECTED_CONFIRMATION, "refs/heads/main")
    assert ok and "aucun deploiement" in msg


def test_no_go_refuse_par_defaut():
    ok, msg = gate.evaluate("NO-GO", "", "refs/heads/main")
    assert not ok and "NO-GO" in msg


def test_phrase_absente_refusee():
    assert not gate.evaluate("GO", "", "refs/heads/main")[0]


def test_phrase_approximative_refusee():
    assert not gate.evaluate("GO", "JE VALIDE LA SIMULATION ", "refs/heads/main")[0]


def test_branche_feature_refusee():
    assert not gate.evaluate("GO", gate.EXPECTED_CONFIRMATION, "refs/heads/feature/any")[0]


def test_ref_absente_refusee():
    assert not gate.evaluate("GO", gate.EXPECTED_CONFIRMATION, "")[0]


def test_valeurs_de_decision_inconnues_refusees():
    assert not gate.evaluate("deploy", gate.EXPECTED_CONFIRMATION, "refs/heads/main")[0]


def test_rapport_mentionne_simulation_uniquement():
    report = gate.report_text(True, "go", "refs/heads/main", "sha-test")
    assert "SIMULATION" in report
    assert "AUCUNE connexion SFTP" in report
    assert "sha-test" in report


def test_mode_demo_independant_des_secrets(monkeypatch):
    for name in ("RELEASE_DECISION", "RELEASE_CONFIRMATION", "GITHUB_REF", "GITHUB_SHA"):
        monkeypatch.delenv(name, raising=False)
    run = subprocess.run([sys.executable, str(SOURCE), "--demo"], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, run.stderr
    assert "HORS LIGNE" in run.stdout
    assert "Aucune connexion OVH" in run.stdout


def test_workflow_strictement_manuel_et_non_deployant():
    workflow = (ROOT / ".github/workflows/ovh-manual-release-gate.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow and "pull_request:" not in workflow
    assert "contents: read" in workflow
    assert "inputs.decision" in workflow and "inputs.confirmation" in workflow
    assert "scripts/ovh_release_gate.py" in workflow
    assert "python -m pytest" in workflow and "php -l contact-submit.php" in workflow
    assert "secrets." not in workflow
    for forbidden in ("sftp -", "rsync ", "scp ", "ssh -", "curl -T", "ftp -"):
        assert forbidden not in workflow.lower()
