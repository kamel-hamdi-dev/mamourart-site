"""Mission 26: validation manuelle pour simulation GitHub Actions, SANS acces OVH.

Ne lit aucun secret et ne contient ni reseau, ni transfert, ni restauration.
La decision GO ne concerne QUE le lancement de verifications locales en simulation.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

EXPECTED_CONFIRMATION = "JE VALIDE LA SIMULATION"
REQUIRED_REF = "refs/heads/main"


def evaluate(decision: str, confirmation: str, ref: str) -> tuple[bool, str]:
    if ref != REQUIRED_REF:
        return False, "REFUS : la simulation manuelle doit partir de main"
    if decision != "GO":
        return False, "NO-GO : execution bloquee, aucune publication"
    if confirmation != EXPECTED_CONFIRMATION:
        return False, "REFUS : phrase de confirmation de simulation incorrecte"
    return True, "GO valide pour TESTS ET RAPPORTS UNIQUEMENT - aucun deploiement"


def report_text(ok: bool, reason: str, ref: str, revision: str) -> str:
    return "\n".join([
        "# Mamourart - Validation manuelle Go / No-Go (SIMULATION)",
        "",
        "**AUCUNE connexion SFTP, sauvegarde OVH, restauration ou publication.**",
        "",
        f"Decision : **{'GO SIMULATION' if ok else 'NO-GO / REFUS'}**",
        f"Branche : `{ref}`",
        f"Revision : `{revision}`",
        f"Resultat : {reason}",
        "",
        "Une veritable publication necessite un workflow distinct, des protections",
        "et une autorisation explicite supplementaire. Ce module n'en est pas un.",
        "",
    ])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gate manuel de simulation, sans reseau ni secrets")
    parser.add_argument("--demo", action="store_true", help="Affiche uniquement le comportement, sans rapport")
    parser.add_argument("--report", type=Path, default=Path("reports/ovh-manual-release-gate.md"))
    args = parser.parse_args(argv)
    if args.demo:
        print("MISSION 26 : DEMONSTRATION GO / NO-GO HORS LIGNE")
        print("Aucune connexion OVH, aucun mot de passe, aucun deploiement.")
        for decision, phrase in (("NO-GO", ""), ("GO", EXPECTED_CONFIRMATION)):
            _, message = evaluate(decision, phrase, REQUIRED_REF)
            print(f"{decision} : {message}")
        return 0
    decision = os.environ.get("RELEASE_DECISION", "NO-GO")
    confirmation = os.environ.get("RELEASE_CONFIRMATION", "")
    ref = os.environ.get("GITHUB_REF", "")
    revision = os.environ.get("GITHUB_SHA", "indeterminee")
    ok, message = evaluate(decision, confirmation, ref)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report_text(ok, message, ref, revision), encoding="utf-8")
    print(message)
    print(f"Rapport local : {args.report}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
