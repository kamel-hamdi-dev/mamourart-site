"""Mission 26: controle prealable STRICTEMENT HORS LIGNE (pas de mot de passe).

Ce fichier n'ouvre aucune connexion, n'execute aucune restauration et n'ecrit rien.
L'empreinte attendue est la valeur observee avec FileZilla le 18/10/2026 :
elle ne constitue PAS une certification independante d'OVHcloud.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import shutil
import sys
from pathlib import Path

from ovh_deploy_plan import build_plan

HOST = "ftp.cluster129.hosting.ovh.net"
OBSERVED_SHA256 = "xhieLplnoEvvl7+a8sq8wLCh/bvOQvQFIVewi+fK2og"
MIN_FREE_BYTES = 10 * 1024 * 1024


def _within(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def fingerprint_from_known_hosts(path: Path) -> str:
    """Exige une seule cle ed25519 pour notre serveur, sans bibliotheque reseau."""
    found = []
    for line in path.read_text(encoding="ascii").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) != 3:
            raise ValueError("known_hosts : entree invalide")
        host_names, key_type, key_data = parts
        if host_names != HOST or key_type != "ssh-ed25519":
            raise ValueError("known_hosts : serveur ou type de cle non attendu")
        try:
            raw = base64.b64decode(key_data, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("known_hosts : Base64 invalide") from exc
        if len(raw) < 4:
            raise ValueError("known_hosts : cle trop courte")
        label_size = int.from_bytes(raw[:4], byteorder="big")
        if label_size != len(b"ssh-ed25519") or raw[4:4 + label_size] != b"ssh-ed25519":
            raise ValueError("known_hosts : format de cle incompatible")
        if len(raw) != 4 + label_size + 4 + 32:
            raise ValueError("known_hosts : taille ED25519 invalide")
        pub_size = int.from_bytes(raw[4 + label_size:8 + label_size], "big")
        if pub_size != 32:
            raise ValueError("known_hosts : cle ED25519 invalide")
        found.append(base64.b64encode(hashlib.sha256(raw).digest()).decode("ascii").rstrip("="))
    if len(found) != 1:
        raise ValueError("known_hosts : exactement une cle attendue")
    return found[0]


def perform_checks(repo: Path, private_dir: Path, backup_dir: Path, *, disk_free=None):
    """Retourne (verifications, ok), sans modifier l'ordinateur."""
    checks = []

    def check(name, func):
        try:
            detail = func()
            checks.append((name, True, detail))
        except (OSError, ValueError, RuntimeError, TypeError) as exc:
            checks.append((name, False, str(exc)))

    # Ne pas perdre les informations de liens en appelant resolve() trop tot.
    private_redirect = private_dir.is_symlink() or (
        hasattr(private_dir, "is_junction") and private_dir.is_junction())
    backup_redirect = backup_dir.is_symlink() or (
        hasattr(backup_dir, "is_junction") and backup_dir.is_junction())
    repo = repo.resolve()
    private_dir = private_dir.resolve()
    backup_dir = backup_dir.resolve()

    def manifest_check():
        rows = build_plan(repo)
        return f"{len(rows)} fichiers autorises ; {sum(r['bytes'] for r in rows)} octets"

    check("Manifeste public", manifest_check)

    def private_check():
        if not private_dir.is_dir() or private_redirect:
            raise ValueError("dossier prive introuvable ou lien symbolique")
        if _within(private_dir, repo) or _within(repo, private_dir):
            raise ValueError("le dossier prive doit etre separe du depot Git")
        return "dossier separe du depot"

    check("Dossier de configuration prive", private_check)

    def key_check():
        known = private_dir / "known_hosts"
        if known.is_symlink() or not known.is_file():
            raise ValueError("known_hosts introuvable ou lien symbolique")
        fp = fingerprint_from_known_hosts(known)
        if fp != OBSERVED_SHA256:
            raise ValueError("empreinte differente de celle observee le 18/10/2026 ; verifier avec OVH")
        return "empreinte identique a FileZilla (confirmation OVH INDEPENDANTE encore requise)"

    check("Cle publique SSH locale", key_check)

    def backup_check():
        if not backup_dir.is_dir() or backup_redirect:
            raise ValueError("dossier de sauvegardes introuvable ou lien symbolique")
        if (_within(backup_dir, repo) or _within(repo, backup_dir) or
                _within(backup_dir, private_dir) or _within(private_dir, backup_dir)):
            raise ValueError("le dossier de sauvegardes doit etre distinct du depot et des secrets")
        lowered_parts = [part.casefold() for part in backup_dir.parts]
        if any("onedrive" in p or "google drive" in p for p in lowered_parts):
            raise ValueError("dossier cloud detecte ; choisir un dossier prive local")
        return "dossier local distinct"

    check("Dossier de sauvegardes", backup_check)

    def space_check():
        free = disk_free if disk_free is not None else shutil.disk_usage(backup_dir).free
        rows = build_plan(repo)
        min_bytes = max(MIN_FREE_BYTES, 2 * sum(r['bytes'] for r in rows))
        if free < min_bytes:
            raise ValueError("espace libre insuffisant pour deux copies du manifeste")
        return f"{free // (1024 * 1024)} Mio libres (minimum {min_bytes // (1024 * 1024)} Mio)"

    check("Espace disponible", space_check)
    return checks, all(ok for _, ok, _ in checks)


def main(argv=None) -> int:
    base = Path(__file__).resolve().parents[1]
    docs = Path.home() / "Documents"
    parser = argparse.ArgumentParser(description="Controle hors ligne avant sauvegarde Mamourart")
    parser.add_argument("--repo", type=Path, default=base)
    parser.add_argument("--private-dir", type=Path, default=docs / "mamourart-private-sftp")
    parser.add_argument("--backup-dir", type=Path, default=docs / "mamourart-ovh-backups")
    args = parser.parse_args(argv)
    checks, ok = perform_checks(args.repo, args.private_dir, args.backup_dir)
    print("MISSION 26 : CONTROLE HORS LIGNE (aucun acces OVH, aucun secret lu)")
    for label, valid, detail in checks:
        print(f"{'OK' if valid else 'ECHEC'} - {label} : {detail}")
    print("IMPORTANT : empreinte SSH non certifiee independamment par OVHcloud.")
    print("AUCUNE AUTORISATION DE CONNEXION, SAUVEGARDE, RESTAURATION OU PUBLICATION.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
