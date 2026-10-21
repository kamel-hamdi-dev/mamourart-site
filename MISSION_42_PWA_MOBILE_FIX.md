# Mission 42 — Précache sûr et bannière mobile WebP

21 octobre 2026. Corrections des deux anomalies moyennes de Mission 41, sur la
PR [#27](https://github.com/kamel-hamdi-dev/mamourart-site/pull/27) existante.
Aucune fusion, publication, opération OVH/SFTP ou vrai e-mail.

## Références, périmètre et livraison

GitHub vérifié directement avant modification :

| Référence | SHA de départ | État |
|---|---|---|
| PR #27 / `feature/website-v3-2-integration-40` | `fade5c0a72867506d72c09019640233ba3d33e11` | Ouverte, non fusionnée |
| `main` | `f5a5fa17aaa05a6fb73eb3439630c63d08dc3463` | Inchangé |
| PR #25 | `ca18a96b5c7d3508a29615063a0e9411c5329f9e` | Ouverte, non fusionnée |
| PR #26 | `dd2aa66a4573e018c45bf6f02a044ffdfbce5a51` | Ouverte, non fusionnée |

Arbre local propre au départ ; travail uniquement sur la branche autorisée, sans
nouvelle PR, réécriture d'historique ni modification des branches sources.
Code et tests finaux : `4d6e87dd2a6e85c7000b6f3539eb326006efc284`.
Les commits suivants actualisent uniquement ce rapport. Le SHA final de livraison
et ses runs CI sont consignés dans le corps de #27 et le compte rendu final ;
`git rev-parse feature/website-v3-2-integration-40` donne cette tête exacte.
Un rapport ne peut contenir littéralement son propre hash sans le changer.

Onze fichiers modifiés par rapport au SHA de départ, liste exhaustive :

```text
MISSION_42_PWA_MOBILE_FIX.md
en.html
index.html
service-worker.js
tests/browser_mission38.py
tests/browser_mission42.py
tests/test_mission38.py
tests/test_mission42_mobile.py
tests/test_pwa_installation.py
tests/test_service_worker.py
tests/worker_mission42.cjs
```

PHP applicatifs, maintenance, tests PHP, quotas/HMAC, sécurité mail, workflows,
images, manifestes et fichiers Portfolio inchangés octet pour octet.

## A. Reproduction authentique de la faille de précache

Le filtre runtime de v6 ne protégeait pas `cache.addAll()` à l'installation.
Cache Storage n'applique pas automatiquement l'interdiction HTTP `private` ou
`no-store` comme un cache HTTP ordinaire. Une redirection suivie pouvait aussi
produire une réponse 200 marquée `redirected` et être conservée sous l'ancienne URL.

Sur le worker exact de `fade5c0a`, un vrai Chromium et un serveur loopback synthétique
ont reproduit trois installations réussies avec `/legal.html` :

- `Cache-Control: no-store`, réponse et corps synthétiques effectivement en cache.
- `Cache-Control: private`, également en cache.
- Redirection locale vers `/redirect-target.html`, réponse finale 200 avec
  `redirected=true` stockée ; navigation hors ligne vers `/legal.html` produisant
  effectivement `net::ERR_FAILED`.

Les nouvelles assertions Node échouent aussi sur ce worker pour ces trois cas :
12 écritures, `skipWaiting=1` et réponse interdite présente. Le modèle de `addAll`
reproduit ces propriétés au lieu de supposer toutes les réponses sûres.
Ces réponses sont des fixtures locales ; aucune fuite réelle de données n'est
affirmée et aucun serveur public n'a été interrogé.

## A. Correction et politique d'échec

Cache incrémenté de `mamourart-v6` à `mamourart-v7`, car les pages précachées et la
logique d'installation changent. Même stratégie runtime network-first, mêmes
12 ressources essentielles, mêmes URL publiques et nettoyage ciblé.

`cache.addAll()` est remplacé par les étapes suivantes :

1. Vérifier chaque chemin explicite local : origine autorisée, liste publique,
   absence de PHP, query, fragment ou URL réseau relative.
2. Effectuer uniquement des GET revalidés (`cache: no-cache`), avec identifiants
   same-origin et `redirect: error`, sans suivre les redirections d'installation.
3. Valider **tout le lot avant la première écriture** : statut exactement 200,
   type `basic`, URL réseau attendue, corps disponible/non consommé, aucune
   redirection, aucun `private`/`no-store`, aucun `Vary: *`.
4. Écrire séquentiellement les seules réponses validées dans v7.
5. Demander `skipWaiting` seulement après toutes les écritures réussies. Supprimer
   les anciens caches numériques Mamourart uniquement lors de l'activation réussie.

Une erreur HTTP, réseau ou de validation fait échouer l'installation avant ouverture
du cache v7. Une erreur d'ouverture/écriture tente de supprimer uniquement v7 puis
rejette l'installation. Les écritures séquentielles ne peuvent continuer après ce
nettoyage. L'ancien worker et son cache ne sont pas supprimés par ce chemin d'échec.
Si la suppression elle-même échoue, un cache v7 partiel **sûr mais non activé** peut
rester ; aucune garantie absolue de nettoyage physique n'est revendiquée.

Le cache runtime partage les critères de sécurité de réponse, tout en conservant
son comportement réseau et les variantes `lang=fr/en`. La comparaison conserve
origine, chemin et query exacts ; seul le fragment de la requête est retiré car
il n'est pas transmis en HTTP. Un test démontre le cas
`/legal.html?lang=en#privacy-en` avant/après cet ajustement. Les fragments restent
interdits parmi les candidats au précache.

Les exclusions POST/HEAD/OPTIONS, PHP, résultats sent/error, paramètres sensibles,
origines étrangères et ressources non autorisées sont conservées. Une réponse
interdite reçue en runtime reste utilisable en ligne sans être stockée.

## A. Résultats Node et vrai service worker Chromium

**33 nouveaux scénarios Node d'installation réussis**, plus toutes les assertions
runtime précédentes conservées dans `tests/worker_mission42.cjs` et étendues.
Les réponses synthétiques portent réellement statut, headers, type, URL, indicateur
de redirection et corps ; les clones conservent ces métadonnées.

Cas exécutés : 200 normal ; private/no-store/Vary:* ; réponse suivie redirigée ;
301/302/307/308 ; 404/500/503 ; opaque/cors/default/error ; origine/chemin/URL de
résultat inattendus ; URL vide ; corps consommé/absent ; réseau indisponible ;
ouverture/écriture/suppression en échec ; transition de version ; chemins étrangers,
PHP, résultats, query et fragments rejetés avant fetch. Le cas de nettoyage échoué
vérifie explicitement la présence possible d'une seule réponse sûre non activée.
Offline, 503 explicite FR/EN, cache tiers conservé et retour réseau sont vérifiés.

Avec **un vrai service worker Chromium**, pas seulement Node :

| Cas exécutés | Résultat |
|---|---|
| 12 installations interdites/en panne : private, no-store, Vary:*, redirection, 301/302/307/308, 404/500/503, réseau coupé | Worker v7 `redundant`, aucune activation ni cache v7 ; ancien v6 et cache tiers préservés |
| Mise à jour réelle v6 → v7, réponses publiques normales | Activation v7, suppression ciblée de v6, cache tiers conservé |
| Trois mises à jour échouées : no-store, private, redirection | Worker v6 toujours actif, ses documents valides restent disponibles hors ligne |
| Après mise à jour réussie | Cinq documents hors ligne corrects ; éviction d'une démo → 503 explicite ; retour réseau → 200 |

Les types opaques et URL impossibles à produire sans origine externe sont testés
dans Node ; aucune origine externe réelle n'a été contactée pour les simuler.

## B. Analyse et correction de la bannière

Les homepages préchargeaient `banner.webp` mais le media query mobile remplaçait
la déclaration desktop `image-set()` par le seul `banner.png?v=4`.
Le suffixe query n'était pas géré par le worker et empêchait sa restitution offline.

Reproduction Chromium exacte sur v6 : FR/EN à 320 et 390 px demandent WebP **et**
PNG ; CSS calculé sélectionnant le PNG versionné ; corps des deux fichiers
totalisant **1 029 949 octets** (76 404 + 953 545).

Correction minimale dans les deux pages : URL PNG sans suffixe dans le fallback,
puis `image-set()` typé WebP/PNG dans les règles desktop **et mobile**. Le gradient
mobile à 180°, celui desktop à 90°, positions, dimensions, cadrage `cover` et layout
restent inchangés. Préchargement WebP prioritaire existant conservé, aucun second
preload contradictoire. Les images originales n'ont pas été modifiées.

Le PNG n'est pas ajouté au précache : cela déclencherait son téléchargement même
sur les clients WebP. Il reste autorisé dans le cache runtime pour son premier
usage effectif par un navigateur utilisant le fallback.

## B. Résultats réseau, rendu et offline FR/EN

**Huit cas réels Chromium** : index/en × 320/390/768/1440 px. Pour chacun :

- CSS calculé avec `image-set` et chemins sans query.
- Une seule ressource de bannière demandée : `/banner.webp` ; corps de réponse
  effectivement lu, **76 404 octets**, aucun téléchargement PNG.
- Décodage WebP vérifié à 2560 × 1440.
- Aucun débordement horizontal ni erreur JavaScript bloquante.
- Captures après fin des animations examinées : direction premium, cadrage et
  contraste cohérents ; aucun changement majeur de design.

**Quatre parcours mobiles réels** : FR/EN × 320/390. Installation propre v7,
chargement en ligne, passage offline, rechargement du document 200, bannière WebP
précachée effectivement décodée à 2560 × 1440, puis retour en ligne 200. Aucun PNG
demandé pendant l'installation ou ces navigations.

**Quatre simulations explicites du fallback**, deux langues × deux modes :

1. Type MIME WebP remplacé par un type synthétique non pris en charge, dans
   image-set et le preload, pour exercer la sélection réelle du candidat PNG.
2. Déclarations image-set et preload WebP retirés de la fixture pour reproduire
   l'usage des déclarations fallback PNG de production sans les réécrire.

Dans ces fixtures, PNG réellement demandé en ligne, mis en cache runtime sous
worker actif puis décodé hors ligne à 2560 × 1440 ; original de 953 545 octets.
Chromium sait nativement lire WebP : ce ne sont **pas** des essais sur un ancien
navigateur réellement dépourvu de WebP/image-set. Ce dernier reste non vérifié.
Le fallback PNG hors ligne est garanti après son usage en ligne sous le worker
actif, pas par son inclusion au précache initial.

Les octets indiquent les corps des ressources du serveur local synthétique,
pas une mesure LCP, Lighthouse, Core Web Vitals ou un gain de production.

## Non-régression complète et environnement

| Contrôle exécuté | Résultat final |
|---|---|
| Python requis, Node inclus | **163 réussis, 0 échec** : 127 historiques + 33 précache + 3 CSS |
| PHP 8.2.34 | **176 réussis, 0 échec** lors de la relance inchangée |
| Lint PHP complet | **15/15** fichiers valides, applicatifs, maintenance, modules et workers inclus |
| Syntaxe JavaScript / whitespace | `node --check` et `git diff --check` réussis |
| Fixture Chromium 39D originale | 12 contrôles FR/EN/statut/stockage réussis |
| Chromium Mission 38 | Vrai SW, cinq documents offline/503/reprise et 20 combinaisons page/largeur réussis |
| Chromium Mission 40 | 32 statuts, 32 cycles langue/retour, 16 parcours clavier, 16 anciennes URL réussis |

Écart local à conserver : le premier passage PHP a obtenu 175 réussites et un
échec du test des seize demandes identiques concurrentes, dont une réponse était
fausse alors que le test les attend toutes vraies. L'acquisition est volontairement
bornée à 250 ms ; ce résultat est compatible avec une sensibilité du test à la
contention/ordonnancement, sans mesure établissant une cause externe définitive.
La relance du code et des tests strictement inchangés a réussi 176/176. Aucun
timeout, quota, code PHP ni assertion n'a été modifié pour obtenir ce résultat.
Les deux journaux sont conservés ; le succès initial sans incident n'est pas revendiqué.

PHP utilise l'image officielle 8.2.34, digest
`sha256:6dcc2300052741ac45ba9efa2897ddb9f57fd07fd3496d59f78197dbff5384bc`,
conteneur sans réseau externe, non-root, racine/source en lecture seule et tmpfs
privé. Mail natif désactivé pour toute exécution applicative et aucun MTA/sendmail.
Les gardes refusent les invocations intentionnellement non sûres des tests.
Données fictives, registres temporaires et HTTP loopback exclusivement.

Chromium 154.0.8037.57 / Playwright, réseau non local bloqué par routage et résolution
de noms. Aucun PHP exécuté depuis le navigateur, formulaire soumis ou vrai mail.
Python 3.12.14, environnement de test existant ; Node local 24.19.0.
CI existante configurée Python 3.12, Node 22 et PHP 8.2, workflows inchangés.

Commandes reproductibles :

```sh
/workspace/mamourart-site/.venv/bin/python -m pytest -m 'not external' --ignore=tests/test_external_links.py --junitxml=/tmp/mission42-validation/required-junit.xml --tb=short -ra
node tests/worker_mission42.cjs service-worker.js runtime
python3 tests/browser_mission42.py --baseline-only
python3 tests/browser_mission42.py --fixed-only
python3 tests/browser_mission38.py
python3 tests/fixtures/mission39d-browser-proposal.py "$PWD"
python3 tests/browser_mission40.py
# Dans le conteneur PHP isolé uniquement :
php -n -d disable_functions=mail -d allow_url_fopen=0 tests/php/run.php
```

Journaux, JSON de preuves et captures : `/tmp/mission42-validation/`, dont
`node-baseline-results.json`, `chromium42-baseline.json`, `chromium42-fixed.json`,
`browser42-final.log`, `python-required.log`, `required-junit.xml`,
`php-suite-attempt1.txt`, `php-suite.txt`, `php-lint.txt`, `resource-audit.txt`.
Preuves temporaires locales, exclues de toute publication publique.

## Ressources et manifeste

Manifeste public inchangé : **28 fichiers** existants, deux PHP applicatifs inclus,
maintenance privée exclue. Six documents HTML publics, **98 références locales**
et **45 fragments** contrôlés ; les 12 URL précachées appartiennent à la liste
publique. PNG/WebP, anciennes URL et autres pages conservés.
Ni tests, fixtures, rapports, clés, registres HMAC ou temporaires dans le manifeste.
Simulation locale du plan d'inventaire réussie, aucun transfert ni accès OVH.

## GitHub Actions et état final

Les résultats des workflows sur la nouvelle livraison restent à constater après
push dans cette révision initiale du rapport. Les journaux réels seront lus,
indépendamment des seuls badges/étapes, et leurs liens consignés ici et dans #27.
La PR reste ouverte, non fusionnée et sans auto-merge. Seule sa branche est autorisée
au push ; `main` et les deux PR sources doivent conserver les SHA ci-dessus.

## Risques résiduels, limites et problèmes non traités

- Installation volontairement refusée si une seule ressource essentielle ne respecte
  pas le contrat sûr ; l'ancien worker reste actif lors d'une mise à jour ratée.
  Les délais réseau et comportements réels d'hébergement ne sont pas mesurés ici.
- Si le nettoyage d'une écriture échouée est lui-même impossible, cache v7 partiel
  sûr mais non activé possible. Les anciens caches ne sont nettoyés qu'après une
  nouvelle installation réussie ; aucune correction distante de v6 déjà installé
  n'est revendiquée avant cette mise à jour.
- Fallback ancien navigateur vérifié par simulations, pas sur appareil physique
  ou navigateur nativement sans WebP. PNG hors ligne après usage runtime contrôlé.
- Sensibilité locale du test PHP concurrent conservée explicitement ; aucune
  suppression ou modification de test pour la masquer.
- Anomalie faible de traductions accessibles de certaines démos signalée par
  Mission 41 volontairement hors périmètre ; fichiers Portfolio non modifiés.
- Risques sécurité/opérationnels de Mission 40 inchangés : mail non borné sous
  verrou, refus temporaires, saturation globale à huit demandes, IP partagées,
  ambiguïté après acceptation/interruption et absence d'envoi exactement une fois,
  fenêtre de déduplication depuis réservation, identité HMAC limitée, récupération
  autorisée d'anciens registres, maintenance réellement planifiée et limites OVH
  inconnues. Voir aussi `MISSION_40_INTEGRATION_REPORT.md` et la revue 39D.

Pas de production, OVH/SFTP, journaux serveur, secret, délivrabilité mail,
appareil physique, Safari/iOS, Lighthouse/CWV ou publication vérifiés.

## Verdict

**GO conditionnel pour une nouvelle revue indépendante**, sous réserve de CI
verte sur la livraison finale et de l'acceptation des limites documentées.
Les deux anomalies moyennes sont reproduites avant correction et leurs chemins
corrigés sont validés localement. Aucune autorisation de fusion/publication.
Après livraison, attente d'une décision humaine GO/NO-GO.
