# Mission 39D — Corrections après audit 39C

## Étude de conception avant modification

Base de travail vérifiée : PR #26 ouverte, non fusionnée, tête
`0977a3d0656ccbe323b90976af78d8981b950606`. Main inchangé :
`f5a5fa17aaa05a6fb73eb3439630c63d08dc3463`. PR #25 ouverte et indépendante,
tête `ca18a96b5c7d3508a29615063a0e9411c5329f9e`.

| Option | Attente des autres processus | Envoi lent / concurrence | Reprise, finalisation et risques |
|---|---|---|---|
| A : flock bloquant actuel | Non bornée par le code | Tous attendent mail ; doublons et maintenance attendent aussi | Quotas/pending cohérents mais accumulation de workers |
| B : flock non bloquant avec budget court | Budget monotone 250 ms, au plus 26 essais espacés de 10 ms | Rejet générique sans quota après budget ; mail lui-même reste non borné, les demandes distinctes peuvent être temporairement refusées | Même transaction/propriété de finalisation ; pas de nouveaux chemins d'envoi ; reprise pending de 39B conservée |
| C : réservation courte, mail hors verrou, finalisation | Transactions courtes ; transport toujours non borné | Les demandes distinctes peuvent avancer | Il faut un propriétaire exclusif survivant à l'expiration du pending, une finalisation vérifiée et une maintenance compatible. Une simple lease de 300 s permettrait un second envoi si le premier reste vivant. Une coupure après acceptation reste ambiguë sans idempotence du transport |
| D : worker local enfant / interruption transport | Potentiellement délai parent | Fonctions/processus et arrêt effectif du transport non garantis chez OVH | Tuer le parent/enfant n'annule pas un mail déjà accepté ; pas de garantie portable supplémentaire sans configuration/service |

**Choix B**, correction minimale compatible PHP 8.2 sans service, secret ou
configuration OVH nouvelle. L'acquisition n'appelle plus flock bloquant ; tous
les appelants, y compris maintenance, utilisent le même budget. Le budget borne
les tentatives volontaires et leur attente, pas l'ordonnancement OS, les E/S du
système de fichiers ou la durée de mail. Un transport bloqué peut encore rendre
le formulaire indisponible ; cette option réduit l'accumulation de workers et
ne prétend pas résoudre entièrement ce risque. La politique de quota ne change
pas. C n'est pas introduit comme protocole partiel fragile.

La finalisation reste la propriété du processus qui détient le verrou permanent.
Un concurrent ne peut envoyer ni nettoyer son pending. Le quota est publié avant
mail, la fin après mail ; aucune purge d'un état sous opération active. Après
arrêt du processus, le système libère le verrou ; pending reste prudent pendant
300 s, sans confirmation mensongère. Le risque déjà décrit de renvoi après arrêt
entre acceptation mail et finalisation reste inhérent au transport non idempotent.

## Corrections et garanties effectives

### Clé HMAC et migration

Chaque réservation nouvellement publiée contient `key_id`, SHA-256 avec domaine
d'usage de la clé aléatoire de 32 octets. Le JSON ne contient pas cette clé.
Toutes les identités présentes dans l'historique doivent correspondre à la clé
lue sous verrou, y compris avant maintenance et même pour des entrées expirées.
Une substitution de clé de longueur constante, sa perte, une identité incorrecte
ou absente dans une réservation HMAC ferment le registre sans mutation ni envoi.
La suppression des fingerprints à 300 secondes conserve key_id : elle ne permet
pas de contourner la vérification. Aucune régénération avec dépendances actives.

Migration automatique des anciens historiques de quotas SHA-256 de 32 caractères,
sans effacer les réservations : leurs quotas sont comptés puis leurs entrées
liées à la nouvelle identité lors de la publication. Les historiques HMAC de
39B (buckets de 64 caractères ou digest) sans key_id **ne sont pas enrôlés
silencieusement** : il est impossible de savoir si leur clé a déjà été corrompue.
Ils exigent une intervention autorisée. Ce choix peut bloquer un registre 39B
existant ; aucune présence d'un tel registre en production n'est supposée ici.

Récupération à préparer, jamais exécutée dans cette mission : arrêter/drainer les
soumissions, prendre le verrou permanent, vérifier la clé d'origine au moyen
d'une copie de confiance autorisée, contrôler le schéma et les quotas, puis lier
atomiquement chaque ancienne réservation à cette identité vérifiée. Si la clé
n'est pas vérifiable, ne pas fabriquer une identité ni réinitialiser les quotas :
maintenir le refus et demander une décision d'exploitation. Pour revenir à un
état neuf après expiration, il faut aussi vérifier l'absence de tout transport
encore actif ou ambigu. Ne jamais supprimer un verrou pendant des requêtes.
Le code ne fournit pas de voie HTTP ou de passe-droit d'enrôlement/réinitialisation.
Aucun secret n'a été lu ou modifié sur un serveur.

Cette liaison détecte une incohérence accidentelle clé/registre ; ce n'est pas
une signature par une autorité indépendante. Une personne pouvant modifier tous
les fichiers privés peut réécrire clé et identités, ou l'historique entier. La
première liaison d'un historique SHA ne prouve pas rétrospectivement l'intégrité
d'une ancienne clé. Les identifiants restent des pseudonymes : pas une anonymisation.

### Diagnostics et maintenance

`mamourart_contact_diagnostic()` retourne maintenant `disabled`, `ok`, `partial`
ou `error`. Désactivation uniquement si le paramètre facultatif est absent/vide ;
un chemin configuré invalide, public, symlinké ou sans droits privés est une erreur.
Le formulaire ignore ce retour pour ne pas dépendre de la journalisation.
La maintenance le propage. Aucun message utilisateur ne révèle le motif technique.
Les catégories `lock_busy` et `key_integrity` s'ajoutent aux huit précédentes.
Les compteurs restent des minutes observées, pas des nombres de demandes : au
plus **10 écritures par minute** et lecture de 2049 octets pour détecter le
franchissement de la borne utile de 2048. Aucun texte libre ou renseignement
personnel dans les diagnostics. Les dates techniques sont en UTC.

Le schéma des observations est vérifié (jour, catégories, types et bornes).
Un fichier existant vide, corrompu, futur ou trop gros est refusé lors d'une
requête ordinaire. La maintenance peut le réinitialiser sous son verrou non
bloquant, avec un résultat **partiel explicite** signalant les observations perdues.
Elle ne préserve pas le contenu corrompu dans une archive susceptible de croître.
Écritures, troncatures, flush et suppressions sont vérifiés ; pas de succès annoncé
sur une écriture manquée. Les diagnostics restent informatifs, non transactionnels
avec l'envoi ; un arrêt pendant leur écriture peut les endommager.

Le CLI réel `scripts/contact-maintenance.php <racine-publique>` retourne :

| Code | Signification |
|---|---|
| 0 | Travail demandé complet ; diagnostics facultatifs désactivés ou vérifiés |
| 1 | Échec obligatoire : registre inaccessible/incohérent, verrou indisponible, diagnostic configuré en erreur |
| 2 | Racine applicative invalide / usage |
| 3 | Travail partiel : suppression impossible, lot incomplet, verrou diagnostic occupé ou réparation de diagnostic |

Un code 3 exige inspection/nouvelle tentative ; il ne certifie pas la purge.
Aucun contenu personnel n'est imprimé. Le programme refuse un SAPI HTTP avec 404
avant les accès au stockage. Cette branche a été testée par simulation du SAPI,
pas sur un serveur OVH. Les codes CLI ont été testés par de vrais processus PHP.
L'échec unlink est injecté sur une copie de programme namespacée, selon la même
méthode d'isolation que les injections historiques de la suite.

Le CLI utilise un temporaire hors racine publique et le même chemin physique
applicatif que le formulaire. Répertoire 0700, état/clé/verrou 0600. Seuls les
fichiers réguliers correspondant exactement au motif tempnam `.state-` + six
caractères alphanumériques dans le registre privé sont candidats à suppression,
après une heure. Aucun lien, clé, verrou, nom arbitraire `.state-*` ou répertoire
voisin n'est supprimé. Au plus 64 entrées traitées par exécution, avec détection
d'une entrée supplémentaire pour signaler un lot incomplet. Le registre ne doit
pas être partagé avec une autre application. L'itération bornée ne garantit pas
l'absence de famine d'un fichier si un répertoire pollué continue à évoluer ;
le résultat partiel et l'inspection opérateur restent nécessaires.

Rétention logique inchangée : fingerprint 300 s, quota 3600 s ; huit réservations
maximum, JSON borné à 4096 octets. Purge physique au prochain travail réussi.
Avec une maintenance réussie toutes les cinq minutes, sans contention ni lot
incomplet : fingerprints au plus 10 minutes depuis réservation, réservations
au plus 65 minutes, observations au plus 24 h 5 minutes. Sans planification,
en cas de stockage/clé invalide, de verrou occupé ou de code 3, aucune borne de
rétention physique n'est revendiquée. Les répertoires d'initialisation orphelins
restent à inspecter dans une opération autorisée distincte ; leur suppression
arbitraire dans le temporaire parent n'est pas ajoutée. Aucune tâche installée.

### HTTP et protection des ressources

POST uniquement. CONTENT_LENGTH obligatoire, numérique de 1 à 48000 octets.
Seul `application/x-www-form-urlencoded`, facultativement charset UTF-8, est
accepté. Multipart, JSON, types absents/alternatifs et tout fichier envoyé sont
refusés. Le corps est lu avec une borne de 48001 octets ; sa longueur exposée par
PHP doit correspondre à la déclaration. Noms inconnus, doublons, clés tableau,
encodage pourcentage malformé et incohérence entre corps et `$_POST` sont refusés.
Au plus sept paramètres, sans upload ; la comparaison avec le parsing permet de
refuser une troncature ou transformation de champs inattendue par PHP.

Ces vérifications protègent le traitement applicatif, pas le serveur en amont :
HTTP/FastCGI et PHP peuvent déjà avoir parsé/alloué le corps ou tronqué ce qui
est exposé au script. Le code ne peut pas certifier la taille physique reçue par
le serveur. Limites HTTP, post_max_size, max_input_vars, délais et comportement
FastCGI restent à vérifier sur OVH. Chaque champ garde sa borne brute de 14000
octets avant Unicode. UTF-8, unités UTF-16, CRLF/LF, consentement, service,
e-mail et prévention des injections restent testés. Les valeurs du formulaire
HTML normal restent compatibles. Aucun champ linguistique supplémentaire n'est
accepté sur la branche actuelle.

## Vérifications et résultats locaux

Référence auditée : 125 tests PHP et 117 tests Python. Aucun cas historique
supprimé. Les attentes modifiées sont explicites : erreur d'intégrité sur perte
clé, refus de maintenance si cette dépendance est invalide, noms temporaires
réalistes, barrière de test du verrou avec LOCK_NB et tailles HTTP réelles
au lieu de valeurs factices. Le garde du mail natif est étendu aux nouveaux scripts.

| Contrôle | Résultat |
|---|---|
| PHP 8.2.34 `php tests/php/run.php` | **161 réussis, 0 échec** |
| Lint de tous les PHP applicatifs, maintenance et tests | **14 fichiers valides** |
| Python requis, sans sondes réseau | **117 réussis, 0 échec** |
| Deux requêtes concurrentes pendant un transport retenu à la barrière | Doublon et demande distincte refusés avec lock_busy après budget, zéro appel mail supplémentaire, aucune réservation consommée |
| Nettoyage concurrent / finalisation retardée au-delà de 300 s | Refus borné, pending intact, puis finalisation par son propriétaire |
| Arrêts réels de processus avant / après acceptation simulée | Pending conservé, aucun succès mensonger, nouvelle tentative après fenêtre ; ambiguïté du transport explicitement maintenue |
| Clé modifiée d'un bit mais toujours 32 octets | Admission et maintenance refusées, JSON inchangé ; restauration de la clé d'essai rend la déduplication opérationnelle |
| CLI réel | Codes 0, 1, 2 et 3 vérifiés ; purge sans trafic, stockage/chemin incorrect, réparation de diagnostic et travail borné |
| Injection unlink dans le programme CLI namespacé | Code 3, fichier restant ; clé/verrou conservés |
| Pannes mail, exception, admission, finalisation et diagnostics | Refus ou résultat partiel explicite, quotas conservés, verrou libéré |
| Confidentialité, permissions et quotas | Aucun champ personnel brut ajouté ; limites 3/8 conservées |
| `git diff --check` | Réussi |

PHP exécuté dans l'image `php:8.2-cli` déjà utilisée pour 39B, réseau du conteneur
**désactivé**, dépôt en lecture seule. Le lanceur impose `-n`, mail natif désactivé
et URL streams désactivés aux enfants. Tous les mails sont des doubles synthétiques.
Les tests de verrou constatent une durée inférieure à deux secondes (tolérance
CI) et le code borne ses propres tentatives à 250 ms / 26 essais ; cela ne
constitue pas une mesure des délais mail ou du système de fichiers OVH.
Les liens internes, le manifeste public et la confidentialité sont inclus dans
les tests Python existants. Aucun workflow n'est modifié. Les résultats GitHub
Actions sur le SHA de livraison sont à consulter dans la PR et le rapport final,
indépendamment des résultats locaux indiqués ici.

## Intégration simulée avec #25 — proposition, non appliquée aux branches

Arbre temporaire constitué de la combinaison de #25 et #26, puis des corrections
39D. La première exécution Python a reproduit l'audit : **118 réussites et un
échec**, hash figé du formulaire dans `tests/test_mission38.py`.
Aucune absence de conflit Git n'est présentée comme une réussite fonctionnelle.

Dans la simulation uniquement :

- `en.html` reçoit minlength=2 et l'action `contact-submit.php?lang=en`.
- Le PHP retourne `/en.html?...#quoteResult` uniquement pour la valeur exacte
  `en` et une page anglaise locale présente ; toute autre valeur reste française,
  sans destination arbitraire. La validation POST ne gagne aucun champ inconnu.
- Le document statique de retour choisit la langue de confirmation, sans que
  localStorage indisponible ou contenant une préférence ancienne puisse la changer.
- Le hash du formulaire est remplacé par des assertions de structure sémantique
  sur les deux langues : méthode/action/encodage, ensemble exact des champs et
  attributs, min/max, consentement, honeypot, options autorisées, bouton, statut
  accessible, confidentialité et fallback. Sept mutations de sécurité démontrent
  que ces assertions détectent des régressions, au lieu de supprimer le test.
- L'attente d'action du test navigateur optionnel de Mission 38 est adaptée au
  formulaire anglais. Pas de modification du worker, des ressources ou du manifeste.

Après corrections proposées : **127 tests Python réussis**, dont contrôle des
ressources, manifeste de déploiement, SEO et tests Node du cache PWA ; **162 tests
PHP réussis**, incluant le retour anglais et le refus d'une destination arbitraire.
Chromium réel : **12 vérifications de langue/statut**, FR/EN, sent/error, focus,
changement de langue et stockage disponible/refusé. Toutes les requêtes sont
interceptées et servies à partir des fichiers locaux, aucun formulaire soumis.
Les service workers sont bloqués dans ce harnais navigateur ; leur logique et
leurs ressources sont contrôlées séparément par les tests Python/Node de #25.
Le navigateur de Mission 38 avec serveur HTTP/SW réel n'a pas été exécuté ici.

Proposition révisable : `tests/fixtures/mission39d-pr25-integration.patch`.
Ce patch à contexte zéro s’applique avec `--unidiff-zero`. Son application a été vérifiée sur la combinaison temporaire ; elle n'est pas
appliquée au site de cette branche et ne modifie pas la branche #25.
Le harnais autonome est `tests/fixtures/mission39d-browser-proposal.py` ; il prend
le chemin absolu de l'arbre simulé. Ces fichiers ne sont pas dans le manifeste
public. Une intégration future doit appliquer le patch dans un arbre combiné,
exécuter les deux suites et le harnais avant toute décision de fusion.

```text
git apply --unidiff-zero --check <chemin-absolu>/tests/fixtures/mission39d-pr25-integration.patch
git apply --unidiff-zero <chemin-absolu>/tests/fixtures/mission39d-pr25-integration.patch
php tests/php/run.php
<python-pytest> -m pytest -m 'not external' --ignore=tests/test_external_links.py
<python-playwright> <chemin-absolu>/tests/fixtures/mission39d-browser-proposal.py <arbre-simule-absolu>
```

## Fichiers et livraison

Travail exclusivement sur `feature/contact-antispam-mission39b`, PR existante
[26](https://github.com/kamel-hamdi-dev/mamourart-site/pull/26). Aucun nouveau PR,
fusion, déploiement, accès OVH/SFTP, boîte mail ou modification de secret.
Main et branche #25 intacts. Fichiers de la correction 39D :

- `contact-rate-limit.php`, `contact-submit.php`, `scripts/contact-maintenance.php`
- `tests/php/clock-worker.php`, `tests/php/endpoint-worker.php`, `tests/php/fault-functions.php`
- `tests/php/mission39b.php`, `tests/php/suite.php`, `tests/php/mission39d.php`, `tests/php/slow-worker.php`
- `tests/fixtures/mission39d-pr25-integration.patch`, `tests/fixtures/mission39d-browser-proposal.py`
- `MISSION_39B_CONTACT_ANTISPAM.md` (marquage historique), `MISSION_39D_SECURITY_REVIEW.md`

## Risques ouverts et verdict

**A partiellement atténué, pas éliminé** : les autres processus n'attendent plus
indéfiniment le verrou, mais le propriétaire reste dépendant d'un transport
non borné. Une demande distincte peut être refusée et utiliser le fallback e-mail.
Aucune suppression/sur-expiration automatique d'un propriétaire actif n'est ajoutée.
Le risque historique de renvoi après interruption entre acceptation et finalisation
reste documenté ; le nouveau code n'ajoute aucun second chemin d'envoi concurrent.

Le quota global reste saturable par huit demandes distinctes distribuées :
risque **élevé** non résolu. Les prospects derrière une même adresse partagent
toujours trois réservations, et les échecs mail restent comptés. Aucune nouvelle
politique de réputation, hausse de quota ou CAPTCHA appliqué. Réévaluer plus tard
les diagnostics et les options produit/transport dans une décision humaine.

B corrigé par liaison d'identité, avec récupération autorisée pour les anciens
registres HMAC non liés. C corrigé par résultats explicites et contrôles de purge,
mais la rétention physique exige une maintenance réellement opérationnelle.
D renforcé à la frontière applicative, sans garantie sur le parsing amont.
F démontré dans la simulation corrigée ; ses changements restent une proposition.

Avant publication, toujours non vérifiés : durée/timeout mail et PHP, comportement
FastCGI, quotas et limites HTTP/PHP, stockage temporaire privé et partagé entre
workers, atomicité/fiabilité flock/rename sur OVH, persistance après redémarrage,
permissions réelles, planification de maintenance, accès aux diagnostics, migration
et retour arrière. Aucun test de délivrabilité ou de production effectué.

**GO conditionnel pour une nouvelle revue indépendante**, sous réserve de CI
verte sur le SHA livré. Ce verdict ne constitue pas un GO de fusion/publication,
et ne qualifie pas le problème de transport global comme entièrement résolu.
Si une borne de disponibilité complète est exigée, il faudra une décision sur
les garanties de transport et le protocole C avant de poursuivre dans cette voie.
