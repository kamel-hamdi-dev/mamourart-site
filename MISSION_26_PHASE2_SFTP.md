# Mission 26 — Phase 2 : sauvegarde SFTP en lecture seule

**État : développement / essais hors ligne. Aucun déploiement ni restauration.**

Le fichier `scripts/ovh_sftp_snapshot.py` est indépendant du bouton de simulation de la phase 1. La phase 1 reste inchangée.

## Ce qui est préparé

1. Téléchargement SFTP **en lecture seule**, limité aux noms de `deploy-manifest.json` et exclusivement à `/home/mamourl/www`.
2. Refus des liens symboliques, fichiers spéciaux, dossiers et fichiers trop volumineux.
3. Hachage SHA-256 et contrôle de la taille de chaque fichier sauvegardé.
4. `backup-receipt.json` avec l'inventaire des fichiers ; si une erreur survient, la sauvegarde est marquée `INCOMPLETE.txt` et interdite à la restauration.
5. Plan de retour arrière lisible, **sans exécuter de restauration**.
6. Tests hors ligne avec serveur SFTP simulé.

## Commandes sûres, sans aucune connexion OVH

```powershell
python scripts/ovh_sftp_snapshot.py --demo
python -m pytest -m "not external" --ignore=tests/test_external_links.py
```

## Connexion SFTP (NON AUTORISÉE POUR LE MOMENT)

Une connexion réelle demandera une décision distincte. Elle nécessitera :

- `OVH_SFTP_HOST`, `OVH_SFTP_USER`, `OVH_SFTP_PORT` (22 par défaut) ;
- `OVH_SFTP_KEY_FILE` (clé SSH privée conservée hors Git) ;
- `OVH_SFTP_KNOWN_HOSTS` (empreinte du serveur vérifiée par un canal de confiance) ;
- Paramiko installé séparément dans l'environnement d'exécution.

**Aucun mot de passe, aucune clé privée et aucun fichier `known_hosts` ne doivent être publiés dans le dépôt ni copiés dans cette conversation.** Le script utilise une politique stricte de vérification des clés SSH (`RejectPolicy`) et n'active pas le mot de passe comme option.

Le mode réseau `--backup-readonly CHEMIN` ne doit pas être utilisé avant que ces paramètres, les autorisations OVH et la méthode de stockage privé de la sauvegarde soient vérifiés. Une sauvegarde doit rester dans un dossier privé, **hors de `www`, hors du dépôt et hors des artefacts publics GitHub**.

## Non disponible à cette étape

- Aucun upload, remplacement, suppression ou changement de droit OVH.
- Aucun mécanisme de restauration effective (seulement le plan et les contrôles).
- Aucun secret GitHub configuré ; aucun workflow GitHub pour la connexion SFTP.
- Aucune publication déclenchée par un push ou une fusion.

Les futures phases seront validées séparément avec une sauvegarde test, un emplacement privé et une autorisation humaine explicite avant toute opération modifiant OVH.
