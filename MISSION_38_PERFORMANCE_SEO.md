# Mission 38 — performances, PWA et SEO

## Base et audit AVANT

Le 20 octobre 2026, `main` vérifié par le connecteur GitHub :
`f5a5fa17aaa05a6fb73eb3439630c63d08dc3463`, PR #24, identique au HEAD local.
Le transport Git échoue sur le proxy ; livraison via les objets Git du connecteur,
avec ce main comme parent. Branche dédiée : `feature/website-v3-2-performance-seo`.

- Homepage : CSS et JS intégrés, polices système, aucune bibliothèque ou police externe bloquante.
  Bannière CSS sans priorité explicite ; logo en chargement immédiat et sans dimensions HTML.
- Quatre images sous le hero déjà `loading="lazy"` : logo du projet Website,
  dashboard et deux aperçus WebP. Dimensions déjà présentes sauf sur le logo.
- Worker v4 : précache `/`, `index.html`, trois PNG et manifeste ; toute navigation
  non disponible retombe sur la homepage ; toute réponse GET 200 même PHP peut être
  stockée ; activation supprime tous les caches, y compris ceux d'autres applications.
- Manifest : nom, scope `/`, start URL `/`, icônes 192/512 et couleurs cohérents ;
  absence d'identifiant et de langue explicites.
- Homepage HTML uniquement français ; titre, description, canonical et Open Graph FR,
  Twitter summary, robots et sitemap (une seule URL) présents ; aucun hreflang.
  L'anglais dépend du JS et de la préférence navigateur/stockage, avec canonical FR.
  Démonstrations réinitialisées en français ; liens de retour sans continuité EN.
- Déploiement : liste blanche de fichiers à la racine ; aucun sous-répertoire autorisé
  par les scripts existants. Les tests existants citent les PNG officiels et le worker.

## Images : octets réels AVANT / APRÈS

| Ressource sélectionnée par un navigateur WebP | Avant | Après | Gain |
|---|---:|---:|---:|
| Bannière, 2560 × 1440 | 953 545 | 76 404 | 92,0 % |
| Logo officiel, 1254 × 1254 | 997 655 | 724 856 | 27,3 % |
| Dashboard, 1278 × 731 | 57 592 | 55 692 | 3,3 % |
| GPS AI preview, 954 × 650 | 33 680 | 33 680 | inchangé |
| Fret Alerts preview, 954 × 650 | 26 144 | 26 144 | inchangé |
| **Total de ces images** | **2 068 616** | **916 776** | **55,7 %** |

WebP qualité 90 pour bannière/dashboard ; logo WebP sans perte, dimensions conservées.
Les PNG d'origine restent inchangés comme fallbacks : le stockage public des images
augmente donc de 856 952 octets. Les poids ci-dessus représentent les variantes
sélectionnées, pas une mesure réseau/LCP. Aucun score Lighthouse/CWV inventé.
Aperçus différés, non précachés à l'installation ; mise en cache à leur première consultation.
Bannière prioritaire via preload WebP ; CSS image-set avec fallback PNG.

## Ressources textuelles publiques modifiées ou ajoutées (octets)

| Fichier | Avant | Après |
|---|---:|---:|
| `index.html` | 58,891 | 60,236 |
| `en.html` | 0 | 59,477 |
| `legal.html` | 13,518 | 13,662 |
| `gps-ai-demo.html` | 28,191 | 28,508 |
| `fret-alerts-demo.html` | 25,784 | 25,985 |
| `service-worker.js` | 1,515 | 3,278 |
| `manifest.json` | 480 | 526 |
| `sitemap.xml` | 205 | 560 |
| `deploy-manifest.json` | 728 | 801 |
| **Total** | **129,312** | **193,033** |

L'ajout d'une page HTML anglaise augmente ce total sur disque ; une navigation normale
charge une seule version. Aucun paquet JS ajouté.

## PWA et confidentialité

Worker v5 network-first : revalidation HTTP, ressources publiques explicitement
listées, cache versionné propre à l'application ; seules les anciennes clés
`mamourart-vN` sont nettoyées. Précache atomique des documents principaux, logo,
bannière, manifeste et icônes essentielles ; activation après réussite de l'installation.
Aucune substitution de page par la homepage. Une page HTML absente du cache reçoit
une réponse 503 FR/EN explicite hors ligne ; une erreur HTTP en ligne reste une erreur.
Une défaillance d'écriture du cache ne masque pas la réponse réseau.

POST, PHP, résultats de formulaire et paramètres inconnus ne sont pas interceptés.
Réponses privées/no-store, redirigées ou Vary:* non stockées. Les seules variantes
query cacheables sont `lang=fr/en`, car le HTML des pages liées contient les deux langues.
L'identifiant PWA `/`, `lang=fr` et `dir=ltr` sont explicites.

## SEO et navigation

Deux URL statiques réellement disponibles : `/` en français et `/en.html` en anglais.
Le format plat respecte le manifeste et évite tout changement des scripts OVH/SFTP.
HTML visible, titres, descriptions, Open Graph et canonical propres à chaque version,
hreflang réciproques FR/EN et x-default ; sitemap des deux versions. Les textes anglais
proviennent de la traduction existante. Le JSON-LD décrit le même site bilingue.

La langue de l'URL est prioritaire : aucune redirection automatique des moteurs ou
visiteurs selon navigateur. Les boutons changent d'URL et préservent query et fragment.
La préférence est enregistrée quand le stockage est disponible et réutilisée sur le
retour PHP du formulaire ; l'absence de stockage ne bloque plus les scripts.
Les anciennes URL `index.html`, démos et legal restent disponibles. Démos et mentions
légales gardent leurs URL historiques, le paramètre de langue et les liens de retour
vers la homepage correspondante ; aucune fausse URL hreflang pour ces pages JS.
Le formulaire FR reste identique octet pour octet, les deux PHP sont inchangés.

## Vérifications locales

- Python : 117 tests réussis ; `python -m pytest -q -m 'not external' --ignore=tests/test_external_links.py`.
- PHP 8.2 : 91 tests réussis, zéro échec via `php tests/php/run.php` ; mail natif
  désactivé par le lanceur, état temporaire isolé. Lint des deux PHP applicatifs réussi.
- Node : worker exécuté dans un harnais de cache (migration ciblée, documents absents,
  503 FR/EN, erreurs HTTP, private, exclusion POST/PHP/statuts/tokens, cache de langue).
- Tests des ressources/liens locaux et de la liste blanche de déploiement réussis.
- Chromium réel : `python tests/browser_mission38.py` (Playwright et Chromium requis).
  Serveur HTTP local, cinq documents hors ligne, démo évincée → 503, récupération réseau.
  Largeurs 320, 390, 768, 1440 : homepages FR/EN, démos EN, mentions EN ; absence de
  débordement horizontal, menu/Échap et changement d'URL FR/EN, action du formulaire.
  Correction ciblée du bandeau GPS AI qui débordait à 320 px.
- Captures locales temporaires, non livrées ; aucune soumission réelle.
- `git diff --check` ; aucun changement des PHP, scripts OVH/SFTP ou workflows.

## Fichiers livrés

- `MISSION_38_PERFORMANCE_SEO.md`
- `banner.webp`
- `dashboard.webp`
- `deploy-manifest.json`
- `en.html`
- `fret-alerts-demo.html`
- `gps-ai-demo.html`
- `index.html`
- `legal.html`
- `logo.webp`
- `manifest.json`
- `service-worker.js`
- `sitemap.xml`
- `tests/browser_mission38.py`
- `tests/test_mission38.py`
- `tests/test_portfolio.py`

## Limites et revue indépendante

GitHub Actions : résultats à consulter sur le commit et la PR après livraison ;
les contrôles locaux ne constituent pas une confirmation CI. Le rapport final du chat
fournit les liens et conclusions observés.
Aucune vérification OVH, cache de production, SMTP, Safari/iOS ou appareil réel.
Les fallbacks PNG restent lourds sur les navigateurs sans WebP. Vérifier le rendu
sur appareils réels et les optimisations d'images lors de la revue indépendante.
Les deux homepages conservent le même script et la même table de traduction ; les tests
vérifient leur égalité, mais les futurs changements de markup doivent actualiser les deux.
Incrémenter la version du worker à la prochaine modification des ressources publiques.
Les liens externes facultatifs ne sont pas validés localement en réseau.

**GO pour revue indépendante ; aucune fusion autorisée.**
Aucun accès OVH/SFTP, déploiement, publication, changement de sécurité ou envoi de mail.
