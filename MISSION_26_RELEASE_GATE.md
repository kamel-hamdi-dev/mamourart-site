# Mission 26 - Gate Go / No-Go (SIMULATION UNIQUEMENT)

Cette phase ajoute un **nouveau workflow GitHub Actions manuel** :
`.github/workflows/ovh-manual-release-gate.yml`.

## Ce que fait le bouton

- Apparait dans Actions uniquement apres fusion sur `main` (autorisation distincte requise).
- Declenchement **manuel** (`workflow_dispatch`), jamais sur `push` ou `pull_request`.
- Demande une decision `NO-GO` (par defaut) ou `GO`.
- Exige, pour `GO`, la phrase exacte `JE VALIDE LA SIMULATION`.
- Refuse toute execution depuis une branche autre que `main`.
- Si GO est valide : execute les tests Python, valide la syntaxe PHP,
  puis genere l'inventaire public et un rapport de simulation.
- Si NO-GO ou phrase incorrecte : le job echoue volontairement, rien n'est deploye.

**Aucun identifiant OVH, aucun secret GitHub, aucune connexion SFTP, aucune
sauvegarde OVH, aucune restauration, aucun televersement sur le site.**
Un GO sur ce bouton n'autorise **jamais** une publication reelle.

## Test local sans connexion

```powershell
python scripts/ovh_release_gate.py --demo
python -m pytest -m "not external" --ignore=tests/test_external_links.py
```

## Mise en garde

Ce bouton est une demonstration de la procedure humaine Go / No-Go. Un futur
bouton reel de publication demandera sa propre validation, une protection des
environnements GitHub, une sauvegarde OVH verifiee, un mecanisme de restauration
teste et une confirmation independante de l'identite du serveur SSH OVH.
