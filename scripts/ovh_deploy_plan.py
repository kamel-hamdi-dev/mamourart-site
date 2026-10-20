"""Mission 26: plan local/Actions en lecture seule, sans connexion OVH.

Phase 1 : valide une liste blanche de fichiers publics et produit un rapport.
Aucun parametre FTP, identifiant, secret ni operation reseau dans ce script.
"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

ALLOWED_EXTENSIONS = {".html", ".php", ".png", ".webp", ".ico", ".js", ".json", ".txt", ".xml"}
REQUIRED = {"index.html", "contact-submit.php", "contact-rate-limit.php", "legal.html", "service-worker.js"}
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def build_plan(root: Path):
    root = root.resolve()
    manifest = json.loads((root / "deploy-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1:
        raise ValueError("Version du manifest inconnue")
    names = manifest.get("files")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        raise ValueError("Manifest: liste de fichiers incorrecte")
    if len(names) != len(set(names)):
        raise ValueError("Manifest: doublons interdits")
    missing = REQUIRED.difference(names)
    if missing:
        raise ValueError("Manifest: fichiers indispensables manquants: " + ", ".join(sorted(missing)))
    rows = []
    for name in names:
        if (not SAFE_NAME.fullmatch(name) or ".." in name or
                Path(name).suffix.lower() not in ALLOWED_EXTENSIONS):
            raise ValueError(f"Nom non autorise dans le manifest: {name!r}")
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Fichier absent ou lien symbolique interdit: {name}")
        length = path.stat().st_size
        if length < 1 or length > 15 * 1024 * 1024:
            raise ValueError(f"Taille invalide: {name}")
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append({"file": name, "bytes": length, "sha256": checksum})
    return rows


def report_text(rows, revision="local"):
    lines = [
        "# Mamourart OVH — Simulation de publication (Mission 26)",
        "",
        "**AUCUN transfert ni connexion OVH. Aucun secret utilise.**",
        "",
        f"Revision : `{revision}`",
        f"Fichiers autorises : **{len(rows)}** — Total : **{sum(r['bytes'] for r in rows):,} octets**",
        "",
        "| Fichier | Octets | SHA-256 |",
        "|---|---:|---|",
    ]
    for row in rows:
        lines.append(f"| `{row['file']}` | {row['bytes']} | `{row['sha256']}` |")
    lines.extend([
        "",
        "Prochaine phase (non implementee ici) : validation humaine, sauvegarde distante verifiee,",
        "transfert SFTP limite aux fichiers approuves, controle du site et rollback controle.",
        "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Prepare un plan OVH sans aucune action sur le serveur")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path, default=Path("reports/ovh-deploy-plan.md"))
    args = parser.parse_args()
    rows = build_plan(args.root)
    output = report_text(rows, os.environ.get("GITHUB_SHA", "local"))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(output, encoding="utf-8")
    print(f"MISSION 26: SIMULATION UNIQUEMENT - {len(rows)} fichiers, aucun acces OVH")
    print(f"Rapport: {args.report}")


if __name__ == "__main__":
    main()
