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

## Authentification SFTP preparee (CONNEXION REELLE NON AUTORISEE)

FileZilla emploie actuellement SFTP/22 avec **authentification normale par mot de passe** sur l'hebergement OVH Free. Ce mode est maintenant gere par le script, **mais ne doit pas etre lance avant une validation distincte**.

La commande `--demo` et tous les tests restent hors ligne et ne lisent pas les identifiants. La commande `--backup-readonly` est la seule a ouvrir une connexion reseau, lorsqu'elle sera explicitement autorisee.

Configuration envisagee pour une future sauvegarde **en lecture seule** :

- `OVH_SFTP_HOST`, `OVH_SFTP_USER`, `OVH_SFTP_PORT` (22 par defaut) ;
- `OVH_SFTP_KNOWN_HOSTS` : fichier prive de cles publiques du serveur **verifiees independamment**, obligatoire ;
- `OVH_SFTP_AUTH=password` et `OVH_SFTP_PASSWORD` : secret transmis exclusivement par variable d'environnement, sans argument de ligne de commande ;
- alternativement `OVH_SFTP_AUTH=key` et `OVH_SFTP_KEY_FILE` si une cle est prise en charge ; le mode `key` reste le mode par defaut pour compatibilite ;
- Paramiko installe plus tard dans un environnement dedie.

L'absence de mode valide, de secret ou de fichier known_hosts est bloquante. Les modes `key` et `password` ne doivent pas etre melanges. La verification de l'identite du serveur emploie `RejectPolicy`, sans acceptation automatique de nouvelles cles.

**Ne mettez jamais de mot de passe ou cle SSH dans Git, les captures d'ecran, les logs, les rapports ou cette conversation.** Une future automatisation GitHub devra utiliser les secrets et une validation humaine. La sauvegarde restera privee, hors de `www`, hors du depot Git et hors des artefacts publics GitHub. En particulier, ne telechargez pas l'export de `contact-submit.php` dans un espace public.

Le mode reseau `--backup-readonly CHEMIN` demeure **interdit** pour le moment : nous devons d'abord confirmer l'empreinte SSH du serveur par un canal de confiance, le stockage prive et l'autorisation de connexion reelle.

## Non disponible à cette étape

- Aucun upload, remplacement, suppression ou changement de droit OVH.
- Aucun mécanisme de restauration effective (seulement le plan et les contrôles).
- Aucun secret GitHub configuré ; aucun workflow GitHub pour la connexion SFTP.
- Aucune publication déclenchée par un push ou une fusion.

Les futures phases seront validées séparément avec une sauvegarde test, un emplacement privé et une autorisation humaine explicite avant toute opération modifiant OVH.
