# Mission 46 — PWA et fiabilité des tests

## Références vérifiées avant modification

Le 21 octobre 2026, #28 ouverte/non fusionnée au HEAD exact
`934e5b8e1f927ace3169fcd8e2d71ce63138cfc6`, branche
`mission44/pwa-banner-corrections`. Branche dédiée `mission46/pwa-cache-tests`
créée à partir de ce commit, cible de livraison : branche #28.

Références distantes revérifiées inchangées avant livraison :

- main : `f5a5fa17aaa05a6fb73eb3439630c63d08dc3463`.
- #25 ouverte/non fusionnée : `ca18a96b5c7d3508a29615063a0e9411c5329f9e`.
- #26 ouverte/non fusionnée : `dd2aa66a4573e018c45bf6f02a044ffdfbce5a51`.
- #27 ouverte/non fusionnée : `9d6ea125337c8c608858af053c3678f0f1ff1ff9`.

## M43-PWA-02

Le candidat v9 et ses variantes PNG sont isolés des caches v8 actifs.
Toutes les réponses sont encore validées avant la première écriture. À chaque
nouvelle tentative, les entrées résiduelles du candidat sont supprimées, puis
leur absence est vérifiée avant toute insertion. Une suppression impossible
bloque la tentative ; aucun ancien cache n'est nettoyé pendant l'installation.
Les écritures restent séquentielles et la récupération existante est conservée.

Le contenu réellement stocké est ensuite relu : ensemble exact des douze clés,
corps, MIME, structure, métadonnées et décodage des images. La même validation
précède tout nettoyage des anciennes versions et tout clients.claim lors de
l'activation. Un contenu manquant, supplémentaire, illisible ou invalide rejette
la promesse de cycle de vie. Le test Node altère aussi un corps après installation
pour contrôler cette barrière d'activation.

Une panne totale de Cache Storage peut toujours empêcher toute suppression.
Le résidu physique n'est donc pas garanti absent ni supprimé atomiquement.
Le test reproduit cette situation, vérifie le rejet d'une nouvelle tentative
pendant la panne, puis sa récupération après rétablissement. Chromium vérifie
l'ancien document hors ligne, les empreintes inchangées du cache v7, et une
nouvelle installation v9 réussie après ajout d'une clé résiduelle inattendue.
La récupération exige une nouvelle tentative d'installation ; aucune boucle de
réessai permanente n'est introduite. Une éviction externe ou une corruption
ultérieure par le navigateur n'est pas empêchable par ce code. Un échec durant
l'activation ne constitue pas une garantie de retour automatique à l'ancien
worker ; les anciens octets sont préservés avant validation, mais le cycle de
vie reste celui du navigateur. Incrémenter la version pour toute future ressource
publique modifiée reste nécessaire.

## M45-TEST-01

Ancienne assertion : `assert.rejects(promise, undefined)` acceptait n'importe
quelle erreur. Reproduction déterministe : une exception sentinelle indépendante
au début de l'installation faisait réussir le scénario empty-body avec cette
assertion. Le test reconstruit cette assertion historique sans dépendre de
l'historique Git (compatible checkout CI peu profond), puis démontre le rejet
par le harnais corrigé.

Les rejets exigent désormais la cause exacte : URL publique interdite, réponse
non sûre, réseau, ouverture, écriture, ou corruption des octets stockés. Une
exception d'assertion du faux fetch/décodeur ne peut plus compter comme le rejet
attendu. Les événements doivent enregistrer exactement une promesse waitUntil.
Les octets écrits sont comparés aux fixtures binaires officielles, au-delà des
statuts et en-têtes. Le modèle Headers remplace les en-têtes sans dupliquer
Content-Type lors de la reconstruction des réponses stockées.

Huit tests de preuve : reproduction de l'ancien faux positif et sept mutations
rejetées (validation des corps ignorée pour corps vide/flux interrompu, ouverture
ignorée, écritures omises, validation des octets stockés omise, barrière
activation omise, nettoyage initial omis). Aucun test désactivé ou affaibli.
Les scénarios stored-corruption et activation-corruption vérifient séparément
les deux barrières. La panne totale vérifie aussi une reprise sûre.

## Validation locale

Preuves : `validation/mission46/`.

- Python 3.12.14 / Node 24.19.0 : **189 passed**, un test externe désélectionné.
  Inclut 51 scénarios d'installation Node et huit preuves par mutations.
- PHP 8.2.35 extrait dans /tmp, sans installation système : **176/176**,
  mail natif désactivé, états temporaires et doublure locale du transport.
  Premier passage **175/176** : test de seize requêtes concurrentes identiques
  instable ; relance du même code et de la même commande **176/176**.
  Les deux journaux sont conservés ; aucun quota, délai ou PHP modifié.
- Lint PHP complet : **15/15**.
- Chromium réel / Playwright, checkout local isolé : Mission 38 réussie (exit 0,
  script silencieux), Mission 39D **12** cas ; Mission 40 **32** résultats,
  **32** retours/changements de langue, **16** formulaires clavier, **16** URL
  historiques ; aucune soumission réelle ni exécution PHP navigateur.
- Mission 44 étendue : **40** premières visites FR/EN × quatre largeurs × cinq
  scénarios, **10** mises à jour rejetées, **8** rejets runtime, récupération des
  résidus et hors ligne anglais. Cache HTTP effacé avant contrôles offline.
  Cinq reproductions historiques sont aussi conservées dans le JSON.
- Suite Chromium Mission 42 : 12 installations rejetées, quatre transitions
  depuis v6, huit cas responsive FR/EN, quatre simulations de format/CSS et
  quatre parcours mobiles installation/hors ligne/reconnexion réussis. Les
  libellés historiques du journal disent encore v8 ; les assertions et les
  injections ciblent bien v9 dans le script livré.
- SEO, Portfolio, manifeste, liens locaux et formulaires couverts par les tests
  Python et les contrôles navigateur historiques. HTML FR/EN, PHP applicatif,
  images, manifeste et workflows identiques à #28.

## Performances et sécurité

Bannière normale page + installation : **76 404 octets**, un WebP et aucun PNG,
comme #28. Aucun asset public ajouté. Les deux relectures du cache et décodages
supplémentaires augmentent le travail local d'installation/activation ; aucune
mesure de latence garantie ni résultat Lighthouse/CWV revendiqué. Aucun coût
supplémentaire introduit dans le parcours fetch runtime.

Les règles de confidentialité, exclusions PHP/POST/résultats et validations
runtime restent inchangées. Aucun secret, accès OVH/production, vrai e-mail,
déploiement, publication, workflow modifié, force-push ou fusion.

## CI et décision

Les résultats Actions du SHA livré et les journaux réels sont consignés dans
la description finale de la PR et le rapport de livraison. Les workflows
existants exécutent Python/Node et PHP ; lint CI limité à dix fichiers,
Chromium absent. Lint complet quinze fichiers et Chromium sont des contrôles
locaux, aucun workflow n'a été modifié.

GO pour revue indépendante sous réserve des résultats CI finaux. Limites
résiduelles : panne totale de stockage, navigateurs physiques Safari/iOS/Android,
en-têtes/performance d'hébergement non évalués et intermittence du test PHP de
concurrence. Ordre proposé, avec GO humain distinct à chaque étape : nouvelle PR
Mission 46 vers #28, puis #28 vers #27, puis #27 vers main, après contrôles et
revue de chaque nouvel arbre d'intégration. #25/#26 sont déjà intégrées dans
#27 ; ne pas les fusionner une seconde fois. Aucune fusion commencée.
