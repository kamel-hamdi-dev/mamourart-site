# Missions 28 et 32 — limitation du formulaire de contact

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

L'horloge est une fonction injectée, appelée une seule fois après l'acquisition
du verrou. Une requête ayant attendu utilise ainsi l'heure de sa transaction,
sans confondre un ordre d'arrivée différent avec un recul de l'horloge. Les
tests contrôlent cette fonction ; le formulaire fournit une fermeture appelant
`time()`. Un vrai recul produisant des dates futures dans l'historique entraîne
un refus sans modification. Un saut en avant fait expirer les réservations selon
l'horloge murale ; un recul ultérieur reste refusé tant que des dates sont futures.

Une erreur de création, lecture, verrouillage, écriture ou remplacement entraîne
un refus et aucun appel à `mail`. Un fichier d'historique vide (zéro octet),
corrompu, trop volumineux, de structure invalide ou contenant une date future
est également refusé. Une
écriture incomplète laisse l'historique précédent intact. Sa disparition dans un
répertoire déjà publié entraîne un refus. Le quota est réservé
avant `mail` ; un échec d'envoi garde sa réservation, comme auparavant.

## Initialisation et récupération (Mission 32)

Lorsque le répertoire final est absent, un répertoire frère privé
`.mamourart-contact-init-<aléatoire>` est préparé sur le même système de fichiers.
Il contient `state.json` avec `[]` (écriture complète, flush et fermeture vérifiés)
et `lock` déjà créé et fermé. Seul un `rename` du répertoire complet le rend
utilisable. Aucune réservation n'est admise avant cette publication.

Une panne avant publication laisse la destination absente : la requête échoue
et la tentative suivante peut recommencer sans perdre de réservation. Une
interruption après publication laisse un état vide valide. En concurrence, un
seul répertoire est publié ; les perdants utilisent celui du gagnant. Sur le
système POSIX attendu, un répertoire publié non vide ne peut pas être remplacé
par ce `rename`. Le verrou publié reste toujours le même inode.

Une interruption brutale peut laisser un répertoire de préparation orphelin,
jamais utilisé comme historique. Une erreur après publication mais avant la
première réservation laisse également un état vide valide et réutilisable.

Un ancien répertoire v2 contenant seulement `lock`, ou un état publié perdu ou
corrompu, est ambigu : il est impossible d'en déduire qu'aucune réservation n'a
été admise. Il reste donc refusé automatiquement. Pour cette situation, la
procédure opérationnelle suivante exige une autorisation de maintenance séparée ;
elle n'est pas exécutée dans cette mission :

1. Identifier le répertoire exact de cette installation (`$rateDirectory` dans
   `contact-submit.php`). Suspendre les admissions et arrêter/drainer tous les
   processus, y compris les anciennes versions, qui pourraient utiliser cet état.
2. Corriger la panne de stockage et vérifier que l'horloge est fiable. Attendre
   au moins 3 600 secondes réellement écoulées depuis la dernière admission
   possible, tout en maintenant cette suspension. Si cette absence d'admission
   ne peut pas être garantie, conserver le refus et ne pas réinitialiser.
3. Sans supprimer, recréer ou remplacer `lock` ni son répertoire, ouvrir le
   verrou existant en `r+` et prendre `LOCK_EX`. Vérifier qu'aucun autre processus
   ne peut admettre de demande. Si le verrou manque ou est inutilisable, arrêter
   la procédure et demander une intervention adaptée.
4. Seulement après cette période sans admission, écrire `[]` dans un nouveau
   fichier temporaire du même répertoire ; vérifier l'écriture complète, le
   flush et la fermeture, puis remplacer `state.json` par `rename` sous le verrou.
   Toute erreur maintient la suspension et le refus ; aucun fichier existant
   n'est tronqué et le verrou n'est jamais effacé.
5. Libérer le verrou, reprendre uniquement avec la version corrigée et vérifier
   le fonctionnement selon une procédure autorisée. Le délai garantit que toute
   réservation éventuellement perdue a expiré ; l'état n'est jamais remis à zéro
   sur le seul constat de son absence ou de sa corruption.

## Manifeste de livraison (Mission 32)

`deploy-manifest.json` inclut explicitement `contact-submit.php` et
`contact-rate-limit.php`. `scripts/ovh_deploy_plan.py` exige les deux au manifeste
et sur disque, et refuse les liens symboliques. Les règles existantes de noms,
extensions et chemins sensibles ne sont pas élargies. Le validateur calcule
uniquement un plan local ; aucun déploiement n'est déclenché par ces modifications.

## Vérification hors ligne

Avec PHP 8.2 CLI :

```sh
php tests/php/run.php
php -l contact-submit.php
php -l contact-rate-limit.php
python -m pytest -m "not external" --ignore=tests/test_external_links.py
```

La suite PHP utilise des répertoires temporaires propres et des horloges contrôlées.
Elle couvre les refus sans consommation, les autres IP, les deux quotas,
l'expiration, la concurrence, les erreurs de stockage/verrouillage et les
protections de l'endpoint. Le lanceur désactive le vrai `mail` dans ses processus
PHP ; l'endpoint est copié dans le répertoire de test, ses en-têtes et ses appels
mail sont capturés par des doublures. Aucun état de production n'est utilisé.
Les tests ne nécessitent aucun réseau ; ils peuvent s'exécuter dans un conteneur
avec `--network none` et le dépôt monté en lecture seule.

Validation locale Mission 32 : 91 tests PHP réussis sous PHP 8.2.34, 113 tests
Python réussis, syntaxe des dix fichiers PHP vérifiée et `git diff --check`
réussi, aucun échec. Le plan local a également été produit : 24 fichiers publics,
dont exactement les deux PHP requis, sans aucune opération distante. Les tests
de liens externes n'ont pas été exécutés localement ; aucun essai sur
l'hébergement réel ni véritable e-mail n'a été effectué.

## Limites

- Le mécanisme utilise uniquement les fonctions standard de PHP 8.2 et suppose
  un système de fichiers offrant `flock` et le remplacement atomique par `rename`
  dans un même répertoire, ainsi que la publication POSIX d'un répertoire non
  vide sans remplacement d'une destination non vide. La garantie s'applique aux
  processus partageant cet état ; elle ne couvre pas plusieurs serveurs avec
  des répertoires distincts.
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
  garantie par `fflush` et `rename` seuls. L'initialisation corrigée publie toujours
  le couple verrou/état ; un ancien état incomplet ou une perte après publication
  nécessite la procédure ci-dessus. Un crash peut laisser un répertoire de
  préparation ou un snapshot temporaire orphelin, jamais lu comme état.
- Toute future publication devra inclure les deux fichiers PHP. Cette mission
  prépare uniquement une Pull Request : aucun déploiement ni essai de courrier
  réel n'est effectué. Les workflows et paramètres de sécurité restent inchangés.
  L'ajout des tests PHP à la CI peut être proposé séparément.
