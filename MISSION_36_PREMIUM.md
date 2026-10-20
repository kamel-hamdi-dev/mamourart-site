# Mission 36 — Homepage V3.2 Premium

## Base et périmètre

GitHub `main` vérifié le 20 octobre 2026 :
`4b5171251b98134493516df42d24f59c2587333c`, fusion de la PR #23.
La branche distante `feature/website-v3-2-premium` a été créée depuis ce SHA.
La copie locale initiale était à `bb22b6b`. Le transport Git échouant sur
le proxy, les 18 fichiers différents ont été récupérés par le connecteur
GitHub, au SHA immuable de main, avant développement et tests. Le commit local
`487b0ce` est uniquement un instantané de travail ; il ne doit pas être poussé.
Le commit de livraison GitHub a pour parent le véritable main, sans inclure cet
instantané local. L'arbre de base reconstruit est
`16adf864f0a929c15ac408eecc7df2a21ceebf97`.

La PR modifie uniquement `index.html`, les attentes éditoriales de
`tests/test_b2b_homepage.py`, l'ordre attendu dans `tests/test_portfolio.py`
et ce rapport. Aucun changement des PHP, démonstrations, images, service worker,
scripts OVH, manifeste ou workflows dans la PR.

## Résultat

- Palette bleu nuit, blanc, surfaces #F5F7FA et texte #152233 ; accent #1565B0.
- Hero FR/EN validé, CTA principal vers Contact, secondaire vers Portfolio.
- Quatre services décrits par leurs usages professionnels, méthode en cinq étapes.
- Transport Automation et Website en tête ; GPS AI et Fret Alerts identifiés
  comme prototypes utilisant des données fictives ; Desktop Agent et Mes Heures
  regroupés dans une rubrique secondaire.
- Logo et aperçus officiels réutilisés. Aucun visuel ni résultat commercial inventé.
- Présentation du projet de studio et de son fondateur ; formulaire, mentions
  de confidentialité, liens légaux et confirmations conservés.
- Aucune dépendance ajoutée. Animations discrètes et réduction du mouvement conservées.

## Vérifications exécutées

| Contrôle | Résultat |
| --- | --- |
| `.venv/bin/python -m pytest -q -m 'not external' --ignore=tests/test_external_links.py` | 113 réussis |
| PHP 8.2.34 : `php tests/php/run.php` | 91 réussis, 0 échec ; mail natif désactivé et état temporaire isolé |
| `php -l` des deux PHP applicatifs et huit scripts PHP de test | 10 fichiers valides |
| `git diff --check` | Réussi |
| Comparaison du HTML du formulaire avec la base | Identique octet pour octet |
| Comparaison des fonctions JS après la table de traduction | Identiques à la base |
| Chromium, largeurs 320 / 390 / 768 / 1440 px, FR et EN | Aucun débordement horizontal ; sections, six projets, CTA, liens légaux, menu mobile et fermeture Échap vérifiés |
| Confirmations `sent` / `error` dans Chromium | Vérifiées en FR/EN aux quatre largeurs, sans soumission |
| Images | Décodage des images vérifié avant les huit captures ; captures desktop FR et mobile EN inspectées |

Contrôles Chromium par Playwright temporaire hors dépôt. Le navigateur charge
les fichiers locaux par interception de requêtes sur un nom de domaine de test ;
aucune connexion externe ni soumission de formulaire. Le lancement initial dans
le bac à sable a échoué ; le lancement autorisé hors de cette restriction a réussi.
Les captures de travail restent dans `/workspace/scratch/mamourart-v3-2/`.

## Limites et revue humaine

Les liens externes n'ont pas été testés en réseau. Aucun test OVH, SMTP,
publication ou cache de production. Les tests PHP utilisent des doublures mail ;
ils ne prouvent pas la délivrabilité d'un hébergement réel.

La vérification Chromium ne remplace pas une revue Safari/iOS, Android, du zoom
à 200 %, du parcours clavier complet et du contraste avec les outils habituels.
Valider notamment les proportions du logo, les retours à la ligne FR/EN,
la hiérarchie du portfolio et la lisibilité du formulaire sur appareils réels.
Les images, le cache et la continuité linguistique hors homepage restent
réservés aux Missions 37 et 38.

Verdict : **GO pour revue humaine de la PR**. Aucune fusion, publication,
opération OVH/SFTP ou émission réelle d'e-mail effectuée.
