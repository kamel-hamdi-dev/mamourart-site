"""Mission 26 phase 2: SFTP read-only snapshot and offline rollback planning.

There is intentionally NO remote upload, deletion, chmod, rename or restore operation.
No secrets are read unless --backup-readonly is explicitly selected.
Paramiko is optional and imported only for --backup-readonly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from ovh_deploy_plan import build_plan

REMOTE_BASE = "/home/mamourl/www"
MAX_FILE_BYTES = 15 * 1024 * 1024
CHUNK_SIZE = 128 * 1024


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_destination(directory: Path, name: str) -> Path:
    # manifest names have already been checked by build_plan; defend anyway.
    if not name or name in (".", "..") or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError("Nom de fichier non autorise")
    return directory / name


def _copy_stream(stream: BinaryIO, target: Path, expected_length: int) -> dict:
    if expected_length <= 0 or expected_length > MAX_FILE_BYTES:
        raise ValueError("Taille de fichier OVH invalide")
    digest = hashlib.sha256()
    count = 0
    try:
        with target.open("xb") as output:
            while True:
                chunk = stream.read(CHUNK_SIZE)
                if not chunk:
                    break
                count += len(chunk)
                if count > MAX_FILE_BYTES or count > expected_length:
                    raise ValueError("Fichier plus grand que la taille annoncee")
                output.write(chunk)
                digest.update(chunk)
        if count != expected_length:
            raise ValueError("Taille telechargee incomplete")
        return {"file": target.name, "bytes": count, "sha256": digest.hexdigest()}
    except Exception:
        target.unlink(missing_ok=True)
        raise


def _approved_names(repo: Path) -> list[str]:
    return [row["file"] for row in build_plan(repo)]


def backup_from_sftp(sftp, repo: Path, destination: Path, remote_base: str = REMOTE_BASE) -> dict:
    """Read exactly the allowlisted files, verify completeness, write local backup.

    The SFTP connection is passed in to facilitate offline test doubles.
    No remote write method is called anywhere in this module.
    """
    if remote_base != REMOTE_BASE:
        raise ValueError("Repertoire distant OVH non approuve")
    names = _approved_names(repo)
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Destination de sauvegarde deja utilisee")
    # Prevent accidental snapshots under the website source tree.
    repo = repo.resolve()
    if destination == repo or repo in destination.parents:
        raise ValueError("Sauvegarde interdite dans le depot Git")
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    entries = []
    try:
        for name in names:
            remote = posixpath.join(remote_base, name)
            meta = sftp.lstat(remote)  # lstat refuses remote symlinks
            if not stat.S_ISREG(meta.st_mode):
                raise ValueError(f"Fichier distant non regulier ou lien symbolique: {name}")
            target = _safe_destination(destination, name)
            with sftp.open(remote, "rb") as source:
                entries.append(_copy_stream(source, target, int(meta.st_size)))
        receipt = {
            "version": 1,
            "source": "OVH-SFTP-READONLY",
            "remote_base": remote_base,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "files": entries,
        }
        (destination / "backup-receipt.json").write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        verify_snapshot(destination)
        return receipt
    except Exception:
        # Keep incomplete backups visible for investigation; they will fail verification.
        (destination / "INCOMPLETE.txt").write_text(
            "Sauvegarde incomplete : ne PAS utiliser pour restaurer.\n", encoding="utf-8"
        )
        raise


def verify_snapshot(folder: Path) -> dict:
    folder = folder.resolve()
    if (folder / "INCOMPLETE.txt").exists():
        raise ValueError("Sauvegarde incomplete")
    receipt = json.loads((folder / "backup-receipt.json").read_text(encoding="utf-8"))
    if receipt.get("version") != 1 or receipt.get("source") != "OVH-SFTP-READONLY":
        raise ValueError("Recu de sauvegarde non reconnu")
    if receipt.get("remote_base") != REMOTE_BASE:
        raise ValueError("Origine distante inattendue")
    entries = receipt.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Sauvegarde vide")
    seen = set()
    for entry in entries:
        name = entry["file"]
        target = _safe_destination(folder, name)
        if name in seen or target.is_symlink() or not target.is_file():
            raise ValueError("Fichier manquant, duplique ou lien symbolique")
        seen.add(name)
        if target.stat().st_size != entry["bytes"] or file_hash(target) != entry["sha256"]:
            raise ValueError(f"Empreinte ou taille incorrecte: {name}")
    # No unreviewed additional payload should be used in a restore plan.
    actual = {p.name for p in folder.iterdir() if p.name != "backup-receipt.json"}
    if actual != seen:
        raise ValueError("Fichiers supplementaires ou manquants dans la sauvegarde")
    return receipt


def rollback_plan(folder: Path) -> str:
    """Print-only rollback inventory. NEVER writes to OVH."""
    receipt = verify_snapshot(folder)
    lines = [
        "MISSION 26 - PLAN DE RETOUR ARRIERE (LECTURE SEULE)",
        "AUCUNE RESTAURATION NI CONNEXION OVH",
        f"Origine : {receipt['remote_base']}",
        f"Fichiers verifies : {len(receipt['files'])}",
    ]
    lines.extend(f"  {row['file']} ({row['bytes']} octets, sha256:{row['sha256']})" for row in receipt["files"])
    lines.append("Restauration reelle : NON IMPLEMENTEE, autorisation explicite requise.")
    return "\n".join(lines)


def _env_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Configuration SFTP manquante : {name}")
    return value


def _backup_readonly(repo: Path, folder: Path) -> None:
    # This path cannot execute from a GitHub workflow unless added later with approval.
    try:
        import paramiko
    except ImportError as exc:
        raise RuntimeError("Installez paramiko dans un environnement dedie avant la sauvegarde SFTP") from exc
    host = _env_required("OVH_SFTP_HOST")
    user = _env_required("OVH_SFTP_USER")
    known_hosts = Path(_env_required("OVH_SFTP_KNOWN_HOSTS"))
    ssh_key = Path(_env_required("OVH_SFTP_KEY_FILE"))
    if not known_hosts.is_file() or not ssh_key.is_file():
        raise RuntimeError("Fichier de cle SSH ou known_hosts introuvable")
    client = paramiko.SSHClient()
    client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(
            hostname=host, username=user, port=int(os.getenv("OVH_SFTP_PORT", "22")),
            key_filename=str(ssh_key), look_for_keys=False, allow_agent=False,
            timeout=15, auth_timeout=15, banner_timeout=15,
        )
        with client.open_sftp() as sftp:
            receipt = backup_from_sftp(sftp, repo, folder)
        print(f"SAUVEGARDE SFTP EN LECTURE SEULE VALIDEE : {len(receipt['files'])} fichiers")
        print(f"Emplacement local prive : {folder}")
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sauvegarde OVH lecture seule et simulation rollback")
    parser.add_argument("--demo", action="store_true", help="Test SFTP simule, sans reseau ni secret")
    parser.add_argument("--verify", type=Path, help="Verifier une sauvegarde locale existante")
    parser.add_argument("--rollback-plan", type=Path, help="Afficher le plan de retour arriere sans rien modifier")
    parser.add_argument("--backup-readonly", type=Path, help="Telecharger une sauvegarde OVH en lecture seule")
    args = parser.parse_args()
    selected = sum(bool(x) for x in (args.demo, args.verify, args.rollback_plan, args.backup_readonly))
    if selected != 1:
        parser.error("Choisir un seul mode explicite")
    if args.demo:
        print("MISSION 26 PHASE 2 : DEMONSTRATION HORS LIGNE")
        print("Aucune connexion OVH, aucune modification distante, aucun secret utilise.")
        print("Le retour arriere reste en simulation.")
        return
    if args.verify:
        receipt = verify_snapshot(args.verify)
        print(f"SAUVEGARDE VERIFIEE : {len(receipt['files'])} fichiers")
    elif args.rollback_plan:
        print(rollback_plan(args.rollback_plan))
    elif args.backup_readonly:
        _backup_readonly(Path(__file__).resolve().parents[1], args.backup_readonly)


if __name__ == "__main__":
    main()
