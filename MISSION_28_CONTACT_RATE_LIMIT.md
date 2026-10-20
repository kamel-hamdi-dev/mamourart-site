# Mission 28 — limitation du formulaire de contact

Le limiteur précédent incrémentait le quota global avant de vérifier le quota IP.
Une IP déjà refusée pouvait ainsi épuiser les places des autres visiteurs.

## Correction

`contact-submit.php` conserve les validations, le honeypot, les contrôles d'origine,
les limites de taille, les protections d'en-têtes et les redirections existants.
Après validation, `contact-rate-limit.php` réserve une place dans un historique
commun : huit demandes maximum sur les 3 600 dernières secondes, dont trois par
IP. Chaque entrée contient uniquement un horodatage et un hachage de l'IP.

Un verrou exclusif `flock` sur un fichier stable couvre lecture, vérification des
deux quotas et validation de la réservation. Un refus de quota n'écrit rien,
même pour purger les entrées expirées. Le nouvel historique est écrit dans un
fichier temporaire du même répertoire, puis remplace l'ancien par `rename` après
vérification de l'écriture complète, du flush et de la fermeture. Les autres
processus utilisent le même verrou, qui n'est jamais supprimé ou remplacé.

Une erreur de création, lecture, verrouillage, écriture ou remplacement entraîne
un refus et aucun appel à `mail`. Un fichier d'historique vide (zéro octet), corrompu, trop volumineux,
de structure invalide ou contenant une date future est également refusé. Une
écriture incomplète laisse l'historique précédent intact. Un état absent n'est
initialisé que lors de la première création du verrou ; sa disparition avec un
verrou déjà présent entraîne un refus. Le quota est réservé
avant `mail` ; un échec d'envoi garde sa réservation, comme auparavant.

## Vérification hors ligne

Avec PHP 8.2 CLI :

```sh
php tests/php/run.php
php -l contact-submit.php
php -l contact-rate-limit.php
python -m pytest -m "not external" --ignore=tests/test_external_links.py
```

La suite PHP utilise des répertoires temporaires propres et une horloge fixe.
Elle couvre les refus sans consommation, les autres IP, les deux quotas,
l'expiration, la concurrence, les erreurs de stockage/verrouillage et les
protections de l'endpoint. Le lanceur désactive le vrai `mail` dans ses processus
PHP ; l'endpoint est copié dans le répertoire de test, ses en-têtes et ses appels
mail sont capturés par des doublures. Aucun état de production n'est utilisé.
Les tests ne nécessitent aucun réseau ; ils peuvent s'exécuter dans un conteneur
avec `--network none` et le dépôt monté en lecture seule.

Résultats au 20 octobre 2026, sur `main` `bb22b6b` : 66 tests PHP réussis
sous PHP 8.2.34, 100 tests Python réussis, syntaxe des huit fichiers PHP vérifiée,
aucun échec restant. Les tests de liens externes et les essais sur l'hébergement
réel n'ont pas été exécutés. Aucun véritable e-mail n'a été envoyé.

## Limites

- Le mécanisme utilise uniquement les fonctions standard de PHP 8.2 et suppose
  un système de fichiers offrant `flock` et le remplacement atomique par `rename`
  dans un même répertoire. La garantie s'applique aux processus partageant cet
  état ; elle ne couvre pas plusieurs serveurs avec des répertoires distincts.
  Ces propriétés n'ont pas été vérifiées sur l'hébergement OVH réel.
- Le répertoire privé est dans `sys_get_temp_dir()`, avec un nom lié au chemin
  de l'application. Un nettoyage complet de ce répertoire ou un changement du
  chemin de l'application réinitialise les quotas ; la suppression du seul état
  entraîne un refus sécurisé. Le fichier `lock` ne doit
  jamais être supprimé pendant que des requêtes utilisent ce répertoire.
- Le format v2 n'importe pas les anciens compteurs séparés. Lors d'un futur
  déploiement autorisé, les quotas repartiront à zéro ; éviter de mélanger les
  anciens et nouveaux processus, et prévoir une heure sans admissions si la
  continuité stricte avec les anciens quotas est nécessaire.
- Une panne du stockage ou une horloge qui recule privilégie le refus sécurisé
  à la disponibilité. La persistance après une panne matérielle n'est pas
  garantie par `fflush` et `rename` seuls. Un crash ou échec de la toute première
  initialisation peut laisser un verrou sans état et maintenir ce refus. Un
  crash peut aussi laisser un snapshot temporaire orphelin, jamais lu comme état.
- Toute future publication devra inclure les deux fichiers PHP. Cette mission
  prépare uniquement une Pull Request : aucun déploiement ni essai de courrier
  réel n'est effectué. Les workflows et paramètres de sécurité restent inchangés.
  L'ajout des tests PHP à la CI peut être proposé séparément.
