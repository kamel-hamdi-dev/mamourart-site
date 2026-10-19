# Mission 26 - Durcissement SFTP (HORS LIGNE)

Branche de travail : `feature/ovh-sftp-security-hardening`.

## Correctifs

- Refus de tout hote autre que `ftp.cluster129.hosting.ovh.net`, utilisateur autre que `mamourl` et port autre que 22.
- Imposition du fichier `known_hosts` du dossier local prive Mamourart.
- Execution obligatoire du Preflight (empreinte SSH, manifeste, isolation, espace libre) **avant** lecture du mot de passe et avant importation/reseau Paramiko.
- Refus de destination hors `Documents/mamourart-ovh-backups/snapshot-...`, deja presente, redirigee ou au nom inattendu.
- Refus explicite des liens symboliques/jonctions de dossiers au Preflight (correction de verification effectuee avant `resolve`).

## Verification locale

```powershell
python -m pytest -m "not external" --ignore=tests/test_external_links.py
python scripts/ovh_sftp_preflight.py
```

Ne **pas** lancer `--backup-readonly` : cela tenterait une connexion reelle, qui necessite un GO distinct.
Les tests fournis sont uniquement hors ligne et utilisent des identifiants fictifs.

## Limites

La correspondance avec l'empreinte observee dans FileZilla n'equivaut pas a une confirmation independante OVHcloud.
Des redirections Windows speciales, des services de synchronisation non identifies et des attaques locales avec changement de repertoire entre controle et ecriture ne sont pas tous detectables.
Le compte distant conserve ses droits OVH, meme si ce programme n'envoie aucune commande d'ecriture.
**Aucune connexion OVH ni publication autorisee par cette preparation.**
