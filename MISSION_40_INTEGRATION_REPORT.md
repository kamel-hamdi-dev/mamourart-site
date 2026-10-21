# Mission 40 — Intégration Website V3.2 premium et sécurité

Date : 21 octobre 2026. Périmètre : préparation d'une nouvelle PR vers `main`,
sans fusion, publication, déploiement, accès OVH/SFTP ni vrai e-mail.

## 1. Références vérifiées et état initial

GitHub a été interrogé avant toute modification (connecteur, puis `git ls-remote`).

| Référence | SHA exact utilisé | État initial |
|---|---|---|
| `main` | `f5a5fa17aaa05a6fb73eb3439630c63d08dc3463` | Identique à la base annoncée |
| PR [#25](https://github.com/kamel-hamdi-dev/mamourart-site/pull/25) | `ca18a96b5c7d3508a29615063a0e9411c5329f9e` | Ouverte, non fusionnée |
| PR [#26](https://github.com/kamel-hamdi-dev/mamourart-site/pull/26) | `dd2aa66a4573e018c45bf6f02a044ffdfbce5a51` | Ouverte, non fusionnée |

Le dépôt initial `/workspace/mamourart-site`, branche locale `work`, était propre
(`git status --porcelain=v1` vide). Aucun changement indépendant déplacé ou écrasé.
Les commits et les inventaires complets des deux PR ont été lus. Les objets ont
ensuite été récupérés par `git fetch` ; aucun historique source n'a été réécrit.

## 2. Méthode Git reproductible et conflits

Arbre isolé `/workspace/mamourart-integration-40`, nouvelle branche exclusivement
depuis le `main` vérifié : `feature/website-v3-2-integration-40`.

```sh
git worktree add -b feature/website-v3-2-integration-40 /workspace/mamourart-integration-40 f5a5fa17aaa05a6fb73eb3439630c63d08dc3463
git -C /workspace/mamourart-integration-40 cherry-pick ca18a96b5c7d3508a29615063a0e9411c5329f9e 0977a3d0656ccbe323b90976af78d8981b950606 dd2aa66a4573e018c45bf6f02a044ffdfbce5a51
```

Correspondance des cherry-picks : `ca18a96b` → `7976f5d`, `0977a3d0` → `b386609`,
`dd2aa66a` → `d3bace3`. Aucun conflit textuel ; l'ajout FR de `minlength="2"`
dans `index.html` a été conservé par la fusion automatique puis inspecté.
L'absence de conflit Git n'a pas été utilisée comme preuve de validation fonctionnelle.

## 3. Patch Mission 39D réellement appliqué

Le rapport `MISSION_39D_SECURITY_REVIEW.md`, le patch complet à contexte zéro et
le harnais navigateur associé ont été lus avant application. Les anciennes lignes
et fichiers correspondaient à la combinaison exacte des sources ci-dessus.

```sh
git apply --unidiff-zero --check tests/fixtures/mission39d-pr25-integration.patch
git apply --unidiff-zero tests/fixtures/mission39d-pr25-integration.patch
git diff --check
```

Les trois commandes ont réussi sans forçage ni rejet. Le diff résultant a été relu,
notamment `back()`, les deux formulaires, leur initialisation linguistique et les
tests PHP. Le site fonctionne avec le code intégré ; aucun patch manuel ultérieur
n'est nécessaire. Les fixtures originales sont conservées comme historique privé.

Différences supplémentaires par rapport au patch proposé :

- Libellés des nouveaux tests marqués comme intégration appliquée.
- Commentaire de `back()` précisant les destinations locales fixes.
- Cache `mamourart-v6` : incrément nécessaire après modification des pages
  précachées, conformément au contrat existant du worker. Architecture inchangée.
- Assertions Node et navigateur adaptées à v6 ; exclusions et pannes de cache
  davantage exercées, sans retirer de test historique.
- Garde d'invocation directe étendu à `integration39d.php` ; 14 tests PHP
  supplémentaires et un harnais Chromium Mission 40 reproductible.

## 4. Formulaires et confirmation FR/EN

Les sept champs métier/techniques, limites, consentement, honeypot, méthode POST,
encodage UTF-8, options de service et attributs d'accessibilité sont alignés.
Le nom impose `minlength="2"` dans les deux pages. Le formulaire anglais utilise
`contact-submit.php?lang=en`, le français `contact-submit.php`.

Seule la valeur exacte `en`, avec le fichier local `en.html` présent, sélectionne
`/en.html?contact_status=...#quoteResult`. Toute autre valeur revient à la
destination française fixe. La destination du formulaire de test protégé conserve
sa priorité. Aucun champ POST linguistique, URL de retour arbitraire ou open redirect
n'a été ajouté. Le statut est exclusivement déterminé par le PHP.

Le document statique de retour choisit la langue, même si localStorage est refusé
ou contient la langue opposée. `sent` et `error` restent visibles et leur message
reçoit le focus. Les changements de langue préservent statut et fragment.
Les assertions sémantiques strictes remplacent le hash figé ; sept mutations de
sécurité prouvent qu'elles détectent les régressions.

## 5. Conservation des fonctions et protections sources

Comparaison Git des octets finaux : `contact-rate-limit.php`, maintenance privée,
et suites Mission 39B/39D identiques à la PR #26. Dans le PHP applicatif de soumission,
seuls la sélection de retour prévue par 39D et son commentaire changent.
Déduplication HMAC 300 s, empreinte des champs validés, clé privée locale, identité
de clé liée aux réservations, refus conservateur des corruptions, quotas 3/IP/h
et 8 globaux/h, réservation atomique, 250 ms/26 essais non bloquants, pending,
échecs mail, diagnostics bornés, validation HTTP/Unicode/injections et consentement
sont conservés. Aucun CAPTCHA, service externe, file de messages ou base ajouté.

Les WebP, fallbacks PNG, métadonnées, canonical/hreflang, sitemap, manifeste PWA,
manifeste public, démos et mentions légales conservent les apports de #25.
Les scripts exécutables des deux homepages restent identiques. Les seules autres
différences applicatives sont celles du correctif FR/EN et le numéro du cache.

## 6. Validation PHP 8.2 isolée

**176 tests réussis, 0 échec ; lint complet 15/15 PHP réussi.**
Les 162 tests de l'intégration historique corrigée sont conservés ; 14 cas s'ajoutent.

PHP 8.2.34, image officielle `php:8.2-cli`, digest
`sha256:6dcc2300052741ac45ba9efa2897ddb9f57fd07fd3496d59f78197dbff5384bc`.
Conteneur `--network none --read-only --user 1000:1000 --cap-drop ALL
--security-opt no-new-privileges`, source montée en lecture seule, `/tmp` en tmpfs.
Mail natif désactivé pour toute exécution applicative, URL streams désactivés ;
aucun binaire sendmail dans l'image. Les invocations intentionnellement non sûres
des scripts de test sont refusées par leur garde avant le code applicatif.
Données fictives et registres temporaires privés exclusivement.

Commande de suite : `php -n -d disable_functions=mail -d allow_url_fopen=0 tests/php/run.php`.
Lint : tous les `*.php`, y compris maintenance, modules et workers.
La CI existante énumère seulement dix fichiers pour son lint ; ses workflows
n'ont pas été modifiés. Le lint complet local couvre les quinze.

Concurrence, doublons, quotas, transport lent synthétique, lock_busy, corruption et
migration HMAC, maintenance, diagnostics, Unicode, stockage défaillant, pending,
interruptions et pannes mail ont été exécutés. Les nouveaux cas contrôlent les
sélecteurs URL/CRLF/tableaux/scalaires, le repli sans `en.html` et la priorité du
formulaire privé. Un vrai serveur PHP sur loopback, à l'intérieur du conteneur
sans réseau externe, vérifie quatre POST FR/EN sent/error : HTTP 303, destination
fixe et `Cache-Control: no-store`. Deux appels au seul double de mail sont observés.

## 7. Validation Python et Node/PWA

**127 tests Python requis réussis, 0 échec**, Python 3.12.14 / pytest 9.1.1.

```sh
python3 -m pytest -m 'not external' --ignore=tests/test_external_links.py --junitxml=/tmp/mission40-validation/required-junit.xml --tb=short -ra
```

HTML, contenu FR/EN, formulaires, SEO, sitemap, hreflang, ressources, liens locaux,
manifestes, accessibilité vérifiable et régressions antérieures sont inclus.
Aucun test externe local ni sonde de production n'a été exécuté.

Le harnais Node s'exécute dans la suite requise (Node local 24.19.0 ; CI configurée
Node 22). Installation réussie/échouée, les 12 entrées de précache, activation,
nettoyage des seuls anciens caches numériques Mamourart, conservation des caches
tiers, offline, 503 FR/EN no-store et reprise réseau passent. POST/HEAD/OPTIONS,
PHP, résultats sent/error sur les deux langues, requêtes sensibles et origines
étrangères ne sont pas interceptés. Les réponses private/no-store/Vary:*, redirigées
ou opaques ne sont pas stockées. Les pannes d'ouverture/lecture/écriture du cache
ne masquent pas une réponse réseau valide. Aucune requête réseau réelle par Node.

## 8. Chromium réel et revue visuelle

Chromium 154.0.8037.57 avec Playwright, exécution locale réelle :

| Harnais | Résultat observé |
|---|---|
| Fixture 39D originale inchangée | 12 contrôles FR/EN/statut/stockage |
| `tests/browser_mission40.py` | 32 cas de statut, 32 cycles langue/retour arrière, 16 parcours clavier, 16 anciennes URL |
| `tests/browser_mission38.py` | 5 documents hors ligne avec vrai service worker, éviction → 503, retour réseau ; 20 combinaisons page/largeur |

Largeurs 320, 390, 768 et 1440 px ; homepages FR/EN, portfolio/projets intégrés,
GPS AI, Fret Alerts et mentions légales. Les confirmations sont entièrement visibles
après la fin bornée du défilement animé et reçoivent le focus à l'arrivée.
Consentement clavier, exclusion du honeypot du parcours Tab, menu mobile/Échap,
absence de débordement horizontal majeur et d'erreurs JavaScript vérifiés.
Captures FR 1440 et EN 390 inspectées : présentation premium B2B cohérente,
message focalisé lisible et prototypes toujours décrits honnêtement.

Les harnais de confirmation servent tous les fichiers par interception locale et
bloquent les SW ; le harnais Mission 38 utilise séparément un serveur loopback
et un vrai SW. Les requêtes non locales sont bloquées. Aucun formulaire navigateur
soumis ni PHP public invoqué. Attente du défilement ajoutée au harnais ; aucune
modification du design. Aucun appareil physique, Safari/iOS ou serveur OVH testé.

Commandes :

```sh
python3 tests/fixtures/mission39d-browser-proposal.py "$PWD"
python3 tests/browser_mission40.py
python3 tests/browser_mission38.py
```

## 9. Ressources, liens et manifeste public

28 fichiers publics uniques et existants ; `contact-submit.php` et
`contact-rate-limit.php` présents. 60 références locales vérifiées sur cinq pages,
y compris ressources CSS/image-set et icônes ; tests des fragments/liens internes
et SEO réussis. Aucune URL publique prévue retirée. Images vérifiées :

| Image | Dimensions PNG = WebP | PNG / WebP, octets |
|---|---|---|
| Bannière | 2560 × 1440 | 953545 / 76404 |
| Logo | 1254 × 1254 | 997655 / 724856 |
| Dashboard | 1278 × 731 | 57592 / 55692 |

Priorité bannière, chargement différé et dimensions de #25 conservés.
Tests, rapports, documentation interne, fixtures, patch, maintenance CLI,
temporaires, clés et états HMAC restent exclus du manifeste. Aucun fichier public
inutile ajouté et aucun script de déploiement modifié.

## 10. GitHub Actions et identification de livraison

PR créée et maintenue ouverte : [#27](https://github.com/kamel-hamdi-dev/mamourart-site/pull/27),
source `feature/website-v3-2-integration-40`, cible `main`, auto-merge désactivé.
Code et tests intégrés figés au commit
`a39e01c345919b05994338cb041ce475b5b7b4e1`.
Première livraison complète code et rapport :
`c42b048fe48bcd5fdb69001716e51858e94a7e26`.
Les commits suivants concernent uniquement ce rapport technique privé.

Résultats GitHub Actions constatés par leurs métadonnées et étapes, tous au SHA
exact `c42b048fe48bcd5fdb69001716e51858e94a7e26` :

| Workflow | Lien du run | Résultat |
|---|---|---|
| Site checks | [39551080918](https://github.com/kamel-hamdi-dev/mamourart-site/actions/runs/39551080918) | success ; Python site checks et External link checks réussis |
| PHP 8.2 syntax check | [39551081024](https://github.com/kamel-hamdi-dev/mamourart-site/actions/runs/39551081024) | success ; lint explicite des dix fichiers et suite PHP réussis |

Les contrôles du SHA final, après cette actualisation documentaire, sont accessibles
dans les [checks de #27](https://github.com/kamel-hamdi-dev/mamourart-site/pull/27/checks).
Le SHA final hexadécimal et ses liens de runs sont inscrits dans le corps de la PR
et dans le compte rendu de livraison, après constat de leur réussite. Le SHA du
commit contenant cette révision du rapport se résout par
`git rev-parse feature/website-v3-2-integration-40` ; il n'est pas auto-inscrit dans
son propre contenu, ce qui changerait à nouveau ce hash.

## 11. Conservation des références et limites d'autorisation

Recontrôle après validations locales : main toujours identique au SHA initial ;
PR #25 toujours ouverte/non fusionnée à `ca18a96b5c7d3508a29615063a0e9411c5329f9e` ;
PR #26 toujours ouverte/non fusionnée à `dd2aa66a4573e018c45bf6f02a044ffdfbce5a51`.
Seule la nouvelle branche a été poussée. Aucun commit sur main,
force-push, fermeture des sources, auto-merge, modification de workflows/secrets/
paramètres GitHub, tâche cron ou déploiement n'a été réalisé.

## 12. Risques résiduels et vérifications OVH non réalisées

1. `mail()` reste sous verrou et sa durée réelle est non bornée ; disponibilité
   complète du formulaire non garantie.
2. Des demandes légitimes sont temporairement refusées lorsque le verrou est occupé.
3. Huit demandes distinctes peuvent saturer le quota global horaire, y compris
   depuis des adresses distribuées. Ce risque élevé demeure.
4. Une adresse réseau partagée peut produire des faux positifs du quota individuel.
5. Après acceptation du mail puis interruption avant finalisation, l'état reste
   ambigu ; aucun envoi exactement une fois n'est garanti.
6. La déduplication expire 300 secondes depuis la réservation, pas depuis la fin
   du transport ; une demande peut être renvoyée après cette fenêtre.
7. L'identité HMAC détecte une incohérence clé/registre, sans autorité indépendante ;
   elle ne protège pas contre un acteur capable de réécrire tous les fichiers privés.
8. Certains anciens registres HMAC sans identité vérifiable nécessitent une
   récupération explicitement autorisée ; aucun enrôlement/reset silencieux ajouté.
9. La rétention physique dépend d'une maintenance réellement planifiée et réussie ;
   aucun cron installé et aucune borne physique revendiquée sans ce prérequis.
10. Les limites opérationnelles OVH demeurent inconnues : temps mail/PHP/FastCGI,
    limites HTTP/post_max_size/max_input_vars, stockage privé et partagé, permissions,
    flock/rename, persistance, migration/rollback, diagnostics et maintenance.

Aucun accès OVH/SFTP, contrôle de mamourart.com/www.mamourart.com, secret réel,
test de délivrabilité, mesure Lighthouse/CWV ou publication. Les liens externes
informatifs de la CI restent limités au test existant, qui exclut les deux hôtes
de production ; aucun nouveau périmètre de sondes ajouté.

## 13. Inventaire de la PR intégrée

36 fichiers de code/tests/rapports sources, plus ce rapport, soit 37 fichiers
par rapport au main vérifié :

```text
MISSION_38_PERFORMANCE_SEO.md
MISSION_39B_CONTACT_ANTISPAM.md
MISSION_39D_SECURITY_REVIEW.md
MISSION_40_INTEGRATION_REPORT.md
banner.webp
contact-rate-limit.php
contact-submit.php
dashboard.webp
deploy-manifest.json
en.html
fret-alerts-demo.html
gps-ai-demo.html
index.html
legal.html
logo.webp
manifest.json
scripts/contact-maintenance.php
service-worker.js
sitemap.xml
tests/browser_mission38.py
tests/browser_mission40.py
tests/fixtures/mission39d-browser-proposal.py
tests/fixtures/mission39d-pr25-integration.patch
tests/php/clock-worker.php
tests/php/endpoint-worker.php
tests/php/fault-functions.php
tests/php/integration39d.php
tests/php/mission39b.php
tests/php/mission39d.php
tests/php/slow-worker.php
tests/php/suite.php
tests/php/worker.php
tests/test_contact_form.py
tests/test_external_links.py
tests/test_integration39d.py
tests/test_mission38.py
tests/test_portfolio.py
```

Preuves d'exécution locales : `/tmp/mission40-validation/` contient les journaux
PHP/lint, Python/JUnit, Node via pytest, Chromium 38/39D/40, contrôle des ressources,
revue de source et captures. Ces preuves temporaires ne sont pas publiées au site.

## 14. Verdict

**GO conditionnel pour revue indépendante** : validations locales et première CI
intégrée vertes ; vérifier aussi les checks de la tête finale dans la PR après
l'actualisation documentaire et accepter explicitement les risques ci-dessus.
Ce verdict ne constitue aucune autorisation de fusion ou de publication.
La nouvelle PR réunit #25 et #26 pour une décision ultérieure sans les fermer
ni les fusionner automatiquement. Décision humaine GO/NO-GO attendue après livraison.
