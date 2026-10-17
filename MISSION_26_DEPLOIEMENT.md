# Mission 26 — Publication OVH depuis GitHub

## Phase 1 : simulation uniquement

- Un workflow GitHub Actions **manuel** (`OVH - Preparer la publication (simulation uniquement)`).
- Tests Python (y compris controles existants) et syntaxe PHP 8.2.
- Inventaire strict des fichiers publics liste dans `deploy-manifest.json`.
- Rapport GitHub avec noms, tailles et empreintes SHA-256.
- **Aucune connexion OVH, aucun identifiant, aucune sauvegarde, aucun deploiement, aucun rollback a cette phase.**

Le workflow manuel apparaitra dans l'onglet Actions apres fusion explicite sur `main`.
Ne pas confondre simulation et publication.

## Phases suivantes (a developper et valider separement)

1. Ajouter les secrets SFTP OVH via les environnements GitHub (`production`) avec verification de la cle SSH du serveur.
2. Concevoir la sauvegarde OVH hors du dossier public, tester sa restauration avec une copie fictive.
3. Ajouter une commande de publication manuelle limitee aux fichiers du manifest et exigeant une confirmation explicite.
4. Ajouter les controles du site distant et un rollback lance manuellement si besoin.
5. Premier essai en environnement temporaire. Publication reelle seulement avec autorisation.

Ne jamais recopier dans Git les mots de passe, les cles privees, `.htpasswd` ou les secrets OVH.
