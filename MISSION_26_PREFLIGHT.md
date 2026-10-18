# Mission 26 — Controle prealable hors ligne

Cette etape est volontairement **sans connexion reseau**, sans lecture de mot de passe, sans publication et sans restauration.

## Utilisation

Depuis le depot local Mamourart :

```powershell
python scripts/ovh_sftp_preflight.py
python -m pytest -m "not external" --ignore=tests/test_external_links.py
```

Le controle examine :
- la liste blanche et les empreintes des fichiers locaux (via `build_plan` existant) ;
- la separation du dossier de configuration SSH et du depot ;
- le format ED25519 et la correspondance de la cle de `known_hosts` avec l'empreinte precedemment **observee** dans FileZilla ;
- la separation du dossier de sauvegarde et les chemins cloud evidents ;
- l'espace disque disponible pour deux copies de l'inventaire.

**Limites :** il ne peut pas prouver que Google Drive/OneDrive ne synchronisent pas les dossiers, ni que l'empreinte est certifiee par OVH. Une confirmation independante par OVHcloud est toujours en attente. Les ACL et le chiffrement disque ne sont pas audites. Le controle ne lance pas de sauvegarde SFTP et n'est pas une autorisation de le faire.

Aucun nom d'utilisateur, mot de passe ou cle privee n'est ajoute aux fichiers du depot. Le programme n'interprete pas les secrets de l'environnement. Aucune modification aux workflows GitHub Actions existants.
