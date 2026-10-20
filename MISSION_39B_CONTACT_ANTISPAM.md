# Mission 39B — Protection anti-spam du formulaire

> Rapport initial historique du commit audité `0977a3d`. Pour le comportement
> corrigé, les limites et la livraison après audit 39C, voir
> [MISSION_39D_SECURITY_REVIEW.md](MISSION_39D_SECURITY_REVIEW.md).
> Les sections verrou, intégrité HMAC, HTTP et maintenance ci-dessous sont
> remplacées par ce rapport 39D.

## Base, périmètre et livraison

Base GitHub `main` vérifiée le 20 octobre 2026 :
`f5a5fa17aaa05a6fb73eb3439630c63d08dc3463`. Aucun nouveau commit par
rapport au SHA fourni. Branche : `feature/contact-antispam-mission39b`.
Vérification initiale par le connecteur GitHub, puis `git fetch origin main`
réussi avec l'accès réseau autorisé du bac à sable. Aucun secret consulté.
La PR vise `main`, sans fusion ni publication. Son numéro, son SHA de livraison
et les résultats CI sont précisés dans le rapport de livraison.

Fichiers de cette mission :

- `contact-submit.php`
- `contact-rate-limit.php`
- `index.html`
- `scripts/contact-maintenance.php`
- `tests/php/endpoint-worker.php`
- `tests/php/mission39b.php`
- `tests/php/suite.php`
- `tests/php/worker.php`
- `tests/test_contact_form.py`
- `tests/test_external_links.py`
- `MISSION_39B_CONTACT_ANTISPAM.md`

Le manifeste public reste inchangé : les deux PHP applicatifs y figurent déjà.
Le script de maintenance, les tests et ce document ne sont pas publiables par
le manifeste. Aucun changement de design, SEO, PWA, image, démonstration,
workflow, réglage GitHub ou infrastructure. Les tests de liens externes excluent
explicitement `mamourart.com` et `www.mamourart.com` pour ne pas provoquer de
requêtes de CI vers la production ; un test sans réseau vérifie cette exclusion.

## Déduplication et transaction

Fenêtre : **300 secondes**, strictement avant `réservation + 300`.
La même demande à la limite exacte est à nouveau admissible si les quotas le
permettent. La clé de comparaison comprend les cinq valeurs validées : nom,
entreprise, e-mail, service, description. Les espaces périphériques sont retirés
comme auparavant ; les sauts de ligne du textarea sont normalisés en LF comme
le navigateur. Pas de passage en minuscules, comparaison approximative ou
normalisation des accents : une valeur validée différente reste distincte.
La sérialisation JSON évite les ambiguïtés de concaténation. L'adresse réseau
n'entre pas dans l'empreinte : une nouvelle tentative depuis un autre réseau
est également dédupliquée.

Une clé de **32 octets aléatoires**, produite par `random_bytes`, est créée
atomiquement au premier usage, sous le verrou permanent, dans le fichier privé
`key`. Aucune clé de production n'est inventée, reçue par HTTP ou intégrée au
code. Empreinte HMAC-SHA-256 avec domaine d'usage dédié et comparaison
`hash_equals`. Les nouvelles empreintes réseau utilisent un autre domaine HMAC.
Les anciens buckets SHA-256 tronqués restent comptés pendant la migration,
sans remise à zéro des réservations. Les buckets HMAC de 64 caractères
permettent de refuser une clé manquante même après expiration des empreintes.

La clé est distincte du JSON et privée (0600) ; répertoire 0700, état et verrou
0600. Le chemin historique hors racine publique reste
`sys_get_temp_dir()/mamourart-contact-v2-<hash du chemin applicatif>`.
Le verrou garde toujours son inode. L'état conserve au plus huit réservations,
est limité à 4096 octets à la lecture et publié par fichier temporaire + rename.
Aucune base de données ou extension PHP supplémentaire.

Séquence sous verrou exclusif : validation du stockage et de l'horloge,
recherche du doublon **avant** les quotas, vérification des quotas,
publication d'une réservation `sent=false`, appel du mail, puis publication du
résultat. Un doublon `sent=true` renvoie la confirmation habituelle sans appel
mail ni consommation de quota. Un doublon en attente renvoie l'erreur simple.
Le verrou couvre l'appel mail pour empêcher deux envois simultanés et éviter
une seconde mécanique de verrouillage. Cela sérialise aussi les demandes
distinctes : une lenteur de `mail()` peut retarder tous les prospects. Les délais
PHP et le comportement local de mail doivent donc être vérifiés avant publication.

Sur `mail() === false` ou exception, l'empreinte est retirée et une nouvelle
tentative identique est possible immédiatement, **dans les quotas restants**.
La réservation horaire reste consommée, comme auparavant : on ne crée pas un
moyen d'envoyer indéfiniment en provoquant des erreurs. Après trois échecs sur
une même adresse réseau, son quota peut donc toujours bloquer une tentative.

Si la publication initiale échoue, aucun mail ne part. Si la publication finale
échoue, ou si PHP s'arrête après la réservation, l'état reste en attente et la
réponse ne prétend pas que le mail a réussi. Cette demande peut être bloquée
jusqu'à cinq minutes. Un mail ayant effectivement été accepté avant un arrêt
peut être renvoyé après cette fenêtre : pas de garantie « exactement une fois »
entre un système de fichiers et `mail()`. Un retour vrai de mail prouve seulement
la prise en charge locale, jamais la livraison à la boîte destinataire.

Un redémarrage conservant les fichiers conserve les protections ; une perte
complète du stockage temporaire réinitialise l'historique comme avant. Un état
manquant/corrompu, une clé manquante avec historique HMAC, un lien symbolique
ou une horloge rétrograde bloquent les admissions sans remise à zéro.
Ne pas remplacer la clé ni supprimer le verrou pendant le fonctionnement.
Les garanties d'atomicité ne constituent pas une garantie de durabilité face à
une panne électrique : pas de protocole SMTP transactionnel ni de fsync ajouté.

## Confidentialité et conservation

Aucun nom, adresse e-mail, description ou IP en clair dans le stockage technique.
HMAC protège un export isolé du JSON contre les dictionnaires sans la clé.
Une compromission du compte PHP donnant accès à la clé permet des recherches
par dictionnaire ; des instantanés pris sur le même hébergement peuvent corréler
une empreinte identique. Ce sont des pseudonymes, pas des données anonymes.
Les anciennes empreintes réseau non secrètes restent devinables jusqu'à leur
purge. Ne pas sauvegarder ou publier ces fichiers techniques. La clé reste
pendant la vie du registre ; elle n'est pas une donnée saisie par un prospect.

Durées logiques : empreinte 5 minutes, réservation 3600 secondes glissantes.
Le nettoyage lors d'une admission retire les empreintes expirées et les anciennes
réservations. Sans trafic ni planification, les fichiers périmés restent sur disque
(quantité toujours bornée à huit entrées) : ce n'est pas une rétention temporelle
stricte. Pour une purge même sans trafic, prévoir la maintenance privée ci-dessous.

Les temporaires interrompus `.state-*` de plus d'une heure sont nettoyés sous
le verrou ; chaque maintenance examine **au plus 64 entrées** du répertoire.
Les temporaires d'initialisation dans le parent `.mamourart-contact-init-*`,
hérités de la conception précédente, peuvent rester après un arrêt brutal.
Leur inspection/nettoyage appartient à l'exploitation, hors processus actifs ;
le code ne supprime pas arbitrairement des répertoires voisins d'autres sites.
Le délai de purge des orphelins dépend donc du volume et de l'exploitation.

## Diagnostics désactivés par défaut

Configurer facultativement `MAMOURART_CONTACT_DIAGNOSTICS_DIR` dans
l'environnement PHP avec un chemin **absolu privé précréé**, hors document root,
appartenant au compte PHP et de mode 0700. Ce paramètre n'est pas un secret.
Si ces prérequis ne sont pas réunis, il n'y a pas de diagnostics applicatifs.
Aucun endpoint de lecture n'est ajouté. Ne pas activer de journal PHP public.

Catégories : `validation`, `honeypot`, `individual_quota`, `global_quota`,
`already_processed`, `pending`, `storage_failure`, `mail_failure`.
Les réponses HTTP ne révèlent pas ces catégories : mêmes redirections simples,
honeypot conservant sa confirmation apparente. Aucun texte libre de requête,
identifiant, empreinte, e-mail, IP, stack trace ou message d'exception n'est journalisé.

Un fichier fixe `observations.json`, 0600, contient le jour UTC et, pour chaque
catégorie, la dernière minute observée et le nombre de minutes touchées dans
la journée. **Ce ne sont pas des compteurs de requêtes.** Au plus une écriture
par catégorie/minute, huit par minute ; lecture limitée à 2048 octets et stockage
normal inférieur à cette borne. Verrou non bloquant ; panne ou concurrence des
diagnostics n'altère pas l'admission. Le fichier est réécrit sur place sous son
verrou permanent : une interruption peut perdre des observations ; ce registre
est informatif, pas une source de vérité pour les quotas.

Les observations d'un jour sont remplacées au prochain événement ou passage
de maintenance après minuit UTC. Sans ces passages, elles restent sur disque.
Une erreur de diagnostic n'écrit pas dans un autre journal illimité.

## Maintenance privée à préparer, sans installation dans cette mission

Installer `scripts/contact-maintenance.php` **hors racine publique**, avec une
planification privée toutes les cinq minutes, sous le même compte que PHP.
L'argument CLI est le chemin absolu du répertoire public contenant les deux PHP :

```text
<php-8.2-cli> <chemin-prive>/contact-maintenance.php <racine-publique>
```

Le script ne traite aucune demande et n'appelle jamais mail. Il n'initialise
pas un registre inutilisé, ne réserve aucun quota, ne remplace pas la clé/verrou,
et utilise les mêmes validations, verrou et publication atomique que le formulaire.
Il renvoie 0 en cas de succès, 1 sur panne de stockage et 2 sur mauvais chemin.
Le script refuse les exécutions HTTP (404). Ne pas l'ajouter au manifeste public.
Vérifier que CLI et PHP web utilisent exactement le même `sys_get_temp_dir()`,
le même chemin physique applicatif et le même paramètre de diagnostics.

Avec une exécution réussie toutes les cinq minutes : empreintes supprimées en
au plus 10 minutes depuis réservation, quotas expirés supprimés en au plus
65 minutes, observations journalières en au plus 24 h 5 minutes. Ces bornes
n'incluent pas les arrêts du planificateur, erreurs de stockage ou orphelins en
lot. Sans planificateur vérifié, ne pas revendiquer ces durées physiques.
La mission ne configure pas OVH, ne lance pas ce script en production et ne
vérifie pas la disponibilité de cron ou des variables PHP sur le mutualisé.

## Validation multioctets

Nom : 2–120 unités UTF-16 ; entreprise : 0–120 ; description : 20–3500.
Les caractères accentués/BMP valent une unité, les caractères supplémentaires
(emoji notamment) deux, comme maxlength/minlength HTML. PCRE valide l'UTF-8
avant comptage ; pas de dépendance mbstring/iconv. Les CRLF transportés par
le navigateur sont normalisés en LF pour respecter la longueur du textarea.
L'e-mail reste validé par `FILTER_VALIDATE_EMAIL`, 254 octets maximum.
Injection CR/LF, caractères de contrôle, service non autorisé, tableaux et
consentement absent restent refusés avant stockage et envoi.

Le plafond de requête passe de 12 000 à **48 000 octets**, toujours strict :
3500 caractères BMP peuvent représenter 31 500 octets après encodage URL,
auxquels s'ajoutent noms, entreprise et e-mail. Conserver 12 000 aurait continué
à rejeter des saisies conformes aux limites HTML. Chaque champ brut est aussi
borné à 14 000 octets avant trim et PCRE ; CONTENT_LENGTH malformé est refusé.
Les limites PHP de parsing/post doivent être adaptées par l'exploitation : le
code ne peut pas empêcher l'allocation faite par PHP avant son exécution.

Seule modification HTML : **ligne 590**, ajout de `minlength="2"` au nom,
pour rendre la limite serveur existante visible au navigateur. Aucun autre
élément de formulaire, contenu, traduction, script, style ou attribut ne change.

## Disponibilité : risque résiduel élevé

Les quotas restent **3 par adresse réseau et 8 globalement, sur 3600 secondes**.
La déduplication évite leur consommation par les répétitions accidentelles ou
les bots répétant exactement les mêmes données, même depuis plusieurs IP.
Les refus individuels ne consomment toujours pas de capacité globale.

Huit demandes valides distinctes depuis plusieurs réseaux suffisent encore à
saturer le quota global ; modifier un caractère contourne la déduplication.
Une adresse partagée limite toujours collectivement ses utilisateurs à trois
demandes : le test confirme trois prospects distincts acceptés puis un refus.
Une panne de stockage ferme le formulaire ; elle ne contourne pas les quotas.
Une lenteur mail sous verrou peut également retarder les autres utilisateurs.
Le spam conforme aux validations reste possible, sans preuve d'intrusion.

Aucune correction locale minimale ne distingue de façon fiable un bot distribué
d'un nouveau prospect sans compromis. Pas d'augmentation de quota, liste blanche
basée sur e-mail, passe-droit ou CAPTCHA. Pour décision humaine ultérieure :
évaluer les observations agrégées, puis une vérification indépendante ciblée
ou un challenge adaptatif avec ses impacts disponibilité/confidentialité/coût.
Cela nécessiterait une mission distincte ; aucun Turnstile/CAPTCHA ajouté ici.

## Vérifications reproductibles

Base initiale : **115 tests Python et 91 tests PHP réussis**.
Deux tests supplémentaires sur une copie isolée de cette base reproduisent
les défauts avant correction : deux appels mail pour un doublon, rejet d'un
nom de 120 accents pourtant conforme à maxlength. Résultat attendu de cette
reproduction : 91 réussites, 2 échecs ciblés.

Après correction : **125 tests PHP, zéro échec**, dont concurrence de
16 doublons (un seul mail simulé, une réservation), concurrence de demandes
distinctes (8 au total et au plus 3 par IP), quotas partagés, migration,
reprise après échec mail, corruption/clé perdue/liens symboliques, injection de
pannes d'admission et de finalisation, pending après arrêt, nettoyage et
permissions, diagnostics, données synthétiques et bornes Unicode/CRLF.
Les protections et injections de panne de la PR #23 restent testées.
**12 fichiers PHP** passent le lint, maintenance et nouveau module compris.
**117 tests Python réussis**, y compris exclusion des domaines de production
dans les liens CI, validations statiques du formulaire et tests du site.

Commandes :

```text
php tests/php/run.php
find . -name '*.php' -print0 | xargs -0 -n1 php -l
.venv/bin/python -m pytest -q -m 'not external' --ignore=tests/test_external_links.py
git diff --check
```

PHP absent du système hôte : tests réellement exécutés dans `php:8.2-cli`,
PHP **8.2.34**, image digest
`sha256:118ef4fb1db5e866fb604f2f260da81f819a0a1eac87a4083f9194f48e00beee`,
réseau conteneur désactivé, dépôt monté en lecture seule. Le lanceur impose
`-n`, `disable_functions=mail`, `allow_url_fopen=0` aux enfants. Les seules
fonctions d'envoi utilisées sont des doubles en mémoire/fichiers temporaires
isolés. Aucun véritable e-mail, appel au site ou accès OVH/SFTP.
Les liens externes ne sont pas testés localement en réseau. Aucun test ne
prétend mesurer la délivrabilité, les journaux ou les permissions OVH réelles.
Les workflows existants exécutent la suite étendue via `suite.php`, sans
modification des workflows. Leur état distant doit être lu sur le SHA livré.

## Compatibilité PR #25 et prérequis de publication

PR #25 vérifiée ouverte et non fusionnée, tête
`ca18a96b5c7d3508a29615063a0e9411c5329f9e`.
Les deux PHP, les tests PHP et la maintenance n'y sont pas modifiés.
`deploy-manifest.json` reste intact dans cette mission. L'unique fichier commun
est `index.html` ; l'attribut ajouté concerne une ligne de formulaire qui reste
inchangée dans #25. `git merge-tree --write-tree` entre la livraison de cette mission et cette
tête de #25 réussit sans conflit textuel (arbre combiné
`341a306461c53dfa89e3e7684bdc00241fd8ecb4` avant mise à jour du présent rapport).
La combinaison nécessite encore une revue fonctionnelle ; la branche #25
n’a pas été modifiée. Sa future page `en.html` devra recevoir le même
`minlength="2"` lors de l'intégration des missions ; le serveur protège déjà
cette limite indépendamment du navigateur. Les redirections bilingues futures
restent hors du présent périmètre.

Avant toute publication, avec une autorisation distincte :

1. Revue indépendante des deux PHP, de la migration d'état et des tests.
2. Vérifier PHP 8.2/PCRE/JSON/hash/random_bytes, rename atomique et flock réel
   sur le stockage OVH, identité du compte PHP et chemins hors document root.
3. Vérifier les droits 0700/0600, les capacités disque, le partage du registre
   entre workers, les conditions de redémarrage/purge du temporaire et l'absence
   de lecture HTTP des données techniques. Ne jamais effacer un verrou actif.
4. Vérifier le temps de traitement et les limites d'exécution de mail/PHP sous
   verrou, post_max_size et le plafond HTTP à 48 000 octets.
5. Préparer la maintenance privée, contrôler sa planification et ses erreurs,
   puis vérifier la rétention physique ; diagnostics facultatifs seulement avec
   répertoire privé et configuration vérifiés.
6. Prévoir un retour arrière coordonné : l'ancien PHP ne comprend pas les
   empreintes/buckets HMAC. Ne pas restaurer l'ancien code sur un état nouveau
   en supprimant les quotas actifs ; prévoir arrêt/drainage et revue humaine.
7. Vérifier la combinaison avec #25 et sa page anglaise lors de l'intégration.

Verdict : **GO conditionnel pour revue indépendante**, sous réserve de CI verte
sur le SHA livré ; aucun GO de fusion ou de publication. Le risque de saturation
globale, les délais de mail sous verrou et les prérequis OVH restent explicites.
