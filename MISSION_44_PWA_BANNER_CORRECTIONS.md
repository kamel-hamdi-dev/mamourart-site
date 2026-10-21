# Mission 44 — Corrections V3.2 après contre-expertise Mission 43

## Source, autorisation et isolation

Référence officielle vérifiée sur GitHub le 21 octobre 2026 :
`kamel-hamdi-dev/mamourart-site`, PR #27,
`9d6ea125337c8c608858af053c3678f0f1ff1ff9`.
Les sept constats détaillés de Mission 43 ont été confirmés explicitement
par le donneur d'ordre avant les corrections.

| Référence | SHA vérifié | État initial |
| --- | --- | --- |
| main | `f5a5fa17aaa05a6fb73eb3439630c63d08dc3463` | inchangée |
| PR #25 | `ca18a96b5c7d3508a29615063a0e9411c5329f9e` | ouverte, non fusionnée |
| PR #26 | `dd2aa66a4573e018c45bf6f02a044ffdfbce5a51` | ouverte, non fusionnée |
| PR #27 | `9d6ea125337c8c608858af053c3678f0f1ff1ff9` | ouverte, non fusionnée |

Branche dédiée : `mission44/pwa-banner-corrections`, créée au SHA exact de #27.
Destination de la PR de correction : `feature/website-v3-2-integration-40`.
La branche d'intégration et les trois autres références ne sont pas modifiées.
Le transport initial était bloqué par le bac à sable : les blobs officiels ont
été récupérés via le connecteur GitHub et vérifiés par leur SHA ; arbre exact
`fc8301f5a4ce821f0de03449179eebf4dc57bdf5`, commit original reconstitué à l'identique.
L'historique GitHub a ensuite été récupéré avec l'accès réseau autorisé.

## Résultat des sept anomalies

| Identifiant | Priorité | Statut | Correction et preuve |
| --- | --- | --- | --- |
| M43-PWA-01 | P1 | Corrigée | Lecture complète avant stockage, MIME attendu, UTF-8 strict, structure HTML/manifeste, conteneurs image et décodage réel ; flux interrompus rejetés ; mêmes règles au runtime. Node et Chromium. |
| M43-PWA-02 | P2 | Partiellement corrigée | Si la suppression globale échoue, suppression individuelle des entrées puis nouvelle tentative globale. Une panne totale du stockage peut encore empêcher toute suppression ; cache précédent inchangé, candidat non activé. Deux niveaux de panne testés en Node et vrai Cache Storage. |
| M43-BAN-01 | P1 | Corrigée | `picture` remplace le fond `image-set` ; erreur de décodage WebP → retrait explicite des sources et décodage PNG. Cas WebP 404 et données invalides, FR/EN et quatre largeurs. |
| M43-BAN-02 | P1 | Corrigée | Enregistrement du worker après décodage de la bannière ; précache du format choisi via variante PNG du script. Installation inclut ce format avant activation. Premier rechargement offline testé après effacement du cache HTTP. |
| M43-TEST-01 | P1 | Corrigée | Le faux `Cache.put` consomme le corps avant visibilité de l'entrée, `addAll` consomme aussi les corps ; fixtures réelles et MIME réalistes ; contenus vides, invalides, trop grands, interrompus et mauvais encodage image. Chaque scénario doit afficher son marqueur de fin ; timeout explicite. |
| M43-TEST-02 | P1 | Corrigée | 40 parcours commencent sans contrôleur SW, avec erreurs WebP, vrai Cache Storage, reload offline et retour online ; aucune préinstallation depuis la page harnais. |
| M43-TEST-03 | P2 | Corrigée | La simulation sans `image-set` retire uniquement les déclarations CSS, conserve tout preload existant et reproduit le double transfert du SHA audité. La production utilise désormais `picture` sans preload concurrent. |

Les cinq P1 sont corrigées. Le résidu P2 est annoncé, pas masqué par une
assertion assouplie : la panne totale de suppression doit conserver une entrée
valide non activée dans le test, et laisser v7 strictement inchangé.

## Contrats du worker v8

- Métadonnées conservées : réponse 200/basic, URL publique exacte sans redirection,
  exclusion PHP/POST/résultats/paramètres sensibles, private/no-store/Vary:* refusés.
- Corps lu sur un clone avant toute écriture ; vide, erreur de lecture ou dépassement
  refusés. Plafonds : 512 Kio pour documents/JSON, 2 Mio pour images, au-dessus des
  ressources officielles actuelles. L'annulation d'un clone ne bloque pas sur la
  consommation de la branche originale du flux ; la branche originale d'un
  candidat d'installation rejeté est aussi annulée.
- HTML : `text/html`, UTF-8 strict, doctype/html/title/body et clôtures attendues.
  JSON : `application/json` ou `application/manifest+json`, objet manifeste avec
  nom, start_url/scope publics et icônes PNG de l'allowlist.
- Images : MIME correspondant à l'extension, conteneur WebP/PNG/ICO cohérent,
  décodage `createImageBitmap` réussi, dimensions non nulles, bitmap libéré.
  Ce contrôle structurel n'est ni une signature cryptographique des contenus
  ni un assainissement HTML contre un serveur compromis.
- Toutes les ressources essentielles sont validées avant le premier `put`.
  Les écritures restent séquentielles ; échec → récupération du seul candidat,
  installation rejetée, aucun `skipWaiting`. Le cache précédent reste actif.
- `mamourart-v8` et `mamourart-v8-png` isolent les deux formats lors d'un
  remplacement ; nettoyage seulement après installation valide et uniquement
  des noms Mamourart connus. Les caches tiers sont conservés.
- Au runtime, une réponse invalide reste visible online selon son comportement
  HTTP, mais ne remplace pas la ressource offline validée. Les 503 explicites
  et la navigation FR/EN hors ligne sont conservés.

## Bannière et première visite

L'image décorative utilise un `picture` avec source WebP, image PNG de repli,
dimensions 2560×1440, `fetchpriority=high`, alt vide et parent aria-hidden.
`object-fit:cover`, positions desktop droite/centre et mobile 72%/centre,
et les deux dégradés d'origine sont conservés. Aucun fichier image modifié.
L'absence de preload indépendant évite de contredire le format choisi.

Une erreur WebP n'est plus confiée à `image-set` : le script attend `decode`,
retire les sources en échec, affecte le PNG puis vérifie son décodage. Le worker
est enregistré avec `?banner=png` seulement si le PNG a effectivement été utilisé.
La sélection n'inclut aucune donnée personnelle. Le précache ne télécharge pas
les deux formats. Sa lecture `force-cache` de la bannière réutilise son entrée
HTTP si disponible, avec les mêmes contrôles de confidentialité et de contenu.
Les autres ressources restent revalidées par `no-cache`.

`window.mamourartOfflineReady` représente le décodage et l'activation du worker
incluant le format choisi. Une interruption réseau avant la fin de cette
installation n'est pas une disponibilité offline garantie. Aucun formulaire
ni parcours produit ne dépend de cette promesse de diagnostic.

## Validations locales et preuves

Preuves versionnées dans [`validation/mission44`](validation/mission44/).
Captures inspectées : FR desktop 1440, EN mobile 320, WebP normal et récupération
PNG après WebP invalide ; conservées dans l'espace de travail de la mission.

| Contrôle | Résultat | Preuve |
| --- | --- | --- |
| Baseline Python/Node au SHA audité | 163 réussis | `baseline-python.log` |
| Python/Node final, sélection CI obligatoire | 178 réussis, 0 échec | `python.log`, `python.xml` |
| Scénarios Node de précache | 48 cas, dont contenus/flux et deux niveaux de panne de suppression | `tests/test_pwa_installation.py`, inclus dans les 178 |
| Runtime Node historique étendu | PASS, exclusions et ancien contenu conservés | `tests/test_mission38.py`, inclus dans les 178 |
| PHP isolé, mail natif/URL streams désactivés | 176 réussis, 0 échec | `php-loopback.json` |
| Lint PHP complet | 15/15 | `php-lint.log` |
| Chromium Mission 38 | 5 documents offline, 503/reonline, 20 combinaisons page/largeur, menu/FR/EN | `browser38.log` |
| Chromium 39D | 12 parcours langue/statut, stockage autorisé/refusé | `browser39d.log` |
| Chromium Mission 40 | 32 confirmations, 32 cycles langue/retour, 16 formulaires clavier, 16 URL historiques | `browser40.log` |
| Chromium Mission 42 adapté | 12 installations interdites, 4 transitions v6→v8, 8 bannières, 4 simulations indépendantes, 4 parcours mobiles offline/reonline | `browser42.log`, `chromium42.json` |
| Chromium Mission 44 | 5 reproductions au SHA audité, 10 mises à jour avec v7 conservé, 8 rejets runtime, 40 premières visites FR/EN × 320/390/768/1440 | `browser44.log`, `chromium44.json` |
| Formulaires et périmètre protégé | Formulaires FR/EN identiques octet pour octet ; PHP/scripts/workflows/manifeste/images/démos/légal/sitemap inchangés | `resource-audit.json` |
| Diff et syntaxe | `git diff --check`, Node et compilation Python réussis | validations exécutées avant livraison |

L'essai PHP initial en bac à sable a donné 175/176 : le seul échec était
l'allocation du port loopback, interdite dans ce contexte. La même suite,
strictement inchangée, a donné 176/176 avec l'accès loopback autorisé.
Le journal initial est conservé dans `php-sandbox-attempt.json`.
Aucun quota, timeout applicatif, PHP ou test de concurrence n'a été assoupli.

Versions locales : Python 3.12.14, Node 24.19.0, Chromium 154.0.8037.57,
PHP 8.2.32 CLI isolé, sans configuration système. PHP a été extrait de paquets
Debian officiels dans le répertoire de travail. Aucun secret utilisé.
Le harnais Node accepte les images officielles par comparaison exacte des
fixtures car Node n'a pas de décodeur image ; le décodage réel est vérifié
séparément dans Chromium, y compris les images corrompues.

Commandes principales :

```sh
python -m pytest -q -m 'not external' --ignore=tests/test_external_links.py
php tests/php/run.php
python tests/browser_mission38.py
python tests/fixtures/mission39d-browser-proposal.py /chemin/vers/le/depot
python tests/browser_mission40.py
python tests/browser_mission42.py --fixed-only
python tests/browser_mission44.py --output /tmp/mission44-validation
```

PHP `run.php` lance lui-même un interpréteur neuf avec mail et URL streams
désactivés. Les navigateurs ne soumettent aucun formulaire. Les vrais serveurs
de fixtures sont loopback, PHP/POST refusés ; les autres parcours interceptent
des fichiers locaux. Les contrôles SEO/Portfolio/liens locaux/ressources du
manifeste et confidentialité font partie des 178 tests obligatoires.

## Comparaison de performances au SHA audité

Octets de corps réellement servis par le serveur de fixture, première visite
froide jusqu'à l'installation, cache HTTP fonctionnel, aucun routage Playwright
qui désactiverait ce cache. Les 40 cas finaux vérifient les poids exacts.

| Scénario | Référence 9d6ea125 | Mission 44 | Résultat |
| --- | ---: | ---: | --- |
| WebP normal, page + installation | 152 808 (2×76 404) | 76 404 | −50 %, aucun PNG |
| Simulation sans image-set, preload conservé | 1 106 353 (PNG + 2×WebP) | 76 404 | Native picture WebP, aucun transfert concurrent |
| Simulation WebP non supporté | 1 029 949 (PNG + WebP du précache) | 953 545 | PNG seul, désormais disponible au premier reload offline |
| WebP 404 | 24, aucun PNG de récupération | 953 557 | Réponse d'erreur synthétique 12 octets + PNG 953 545 ; récupération fonctionnelle |
| WebP invalide | 24, aucun PNG de récupération | 953 557 | WebP invalide synthétique 12 octets + PNG 953 545 ; récupération fonctionnelle |

La hausse en cas de panne WebP correspond à la récupération effective de
l'image manquante ; elle n'affecte pas le parcours normal. Les fichiers PNG et
WebP gardent leurs poids d'origine. HTML : index 60 351→61 795 octets, anglais
59 600→61 044 (+1 444 par document pour le mécanisme de récupération/readiness).
La validation ajoute une lecture et un décodage avant stockage, bornés par les
plafonds indiqués. Aucune mesure Lighthouse, CWV, temps de réponse ou cache OVH
n'est revendiquée ; les nombres excluent en-têtes HTTP et compression réseau.
Si l'hébergement empêche le cache HTTP, un nouveau transfert peut être nécessaire
pour remplir Cache Storage ; une réponse privée/no-store est toujours refusée.

## Livraison, CI et limites

La PR et les résultats GitHub Actions au SHA livré sont renseignés lors de la
livraison. Les journaux des jobs réels doivent être lus, pas seulement leurs badges.
Aucun workflow n'est modifié ; Chromium reste une validation locale reproductible.

Fichiers fonctionnels : `service-worker.js`, `index.html`, `en.html`.
Tests adaptés : `tests/worker_mission42.cjs`, `tests/test_pwa_installation.py`,
`tests/test_mission38.py`, `tests/test_mission42_mobile.py`, `tests/test_images.py`,
`tests/browser_mission38.py`, `tests/browser_mission42.py`.
Ajouts : `tests/browser_mission44.py`, ce rapport et les preuves
`validation/mission44/*`. La liste exacte est donnée par le diff de la PR.

Risque résiduel PWA-02 : si le navigateur refuse simultanément toute suppression
globale et individuelle, une entrée déjà validée peut rester dans le candidat
non activé. Critère d'acceptation testé : aucune donnée invalide/privée écrite,
aucune activation du candidat, ancien cache inchangé et encore exploitable
offline. La suppression physique ne peut être garantie contre une panne totale
de l'API de stockage. Une récupération ultérieure dépend du rétablissement du
stockage et d'une installation réussie.

Revue indépendante supplémentaire : appareils Safari/iOS et Android réels,
support de `createImageBitmap` pour PNG/WebP/ICO, mode stockage restreint/quota,
inspection visuelle/clavier/zoom/contraste, chronologie d'installation sur réseau
lent, et validation séparée des en-têtes/cache/performance d'hébergement avant
toute éventuelle publication. Les simulations de support ne sont pas des tests
sur un ancien navigateur physique. Aucune vérification OVH/production effectuée.
Les risques mail/HMAC/quota/maintenance des Missions 39D/40 restent inchangés.

Verdict : **GO SOUS RÉSERVES pour revue indépendante de la PR**, sous réserve
de CI finale verte et acceptation explicite du résidu P2 décrit ci-dessus.
Ce verdict n'autorise aucune fusion ni publication. Aucun accès OVH, e-mail
réel, modification de main/#25/#26/#27, secret, permission, workflow, auto-merge,
auto-déploiement ou force-push. **STOP après livraison ; Mission 45 et toute
fusion nécessitent un nouveau GO humain.**
