"""Professional B2B homepage copy, in French and English."""

import re

from tests.checks import parse_page, read_text

HERO = {'fr': {'heroTitle': 'Des logiciels sur mesure pour vos opérations métier.',
        'heroText': 'Applications métier, interfaces web et automatisations : des solutions '
                    'pensées autour de vos processus, du cadrage aux premières démonstrations.',
        'ctaServices': 'Explorer les projets',
        'ctaProject': 'Parler de votre besoin'},
 'en': {'heroTitle': 'Custom software for your business operations.',
        'heroText': 'Business applications, web interfaces and automation designed around your '
                    'workflows, from initial scoping to early demonstrations.',
        'ctaServices': 'Explore the projects',
        'ctaProject': 'Discuss your needs'}}

SERVICES = {'fr': {'service1Title': 'Applications métier',
        'service1Text': 'Centraliser les dossiers, suivre les opérations et préparer les '
                        'validations dans un outil adapté à votre activité.',
        'service2Title': 'Interfaces web et mobiles',
        'service2Text': 'Donner aux équipes un accès clair aux informations et aux actions utiles, '
                        'au bureau comme en déplacement.',
        'service3Title': 'Automatisation supervisée',
        'service3Text': 'Préparer les tâches répétitives et les décisions à vérifier, en gardant '
                        'une validation humaine sur les actions retenues.',
        'service4Title': 'Connexion d’outils, API et bases de données',
        'service4Text': 'Faire circuler les informations entre vos outils pour limiter les '
                        'ressaisies et rendre les données utilisables.'},
 'en': {'service1Title': 'Business applications',
        'service1Text': 'Centralize records, track operations and prepare approvals in a tool '
                        'designed around your activity.',
        'service2Title': 'Web and mobile interfaces',
        'service2Text': 'Give teams clear access to useful information and actions, at the office '
                        'and on the move.',
        'service3Title': 'Supervised automation',
        'service3Text': 'Prepare repetitive tasks and decisions for review, keeping human approval '
                        'for the selected actions.',
        'service4Title': 'Connecting tools, APIs and databases',
        'service4Text': 'Move information between your tools to reduce duplicate entry and make '
                        'data usable.'}}

STEPS = {'fr': ('Cadrer le besoin',
        'Concevoir le parcours',
        'Développer le périmètre retenu',
        'Tester et valider',
        'Préparer la livraison'),
 'en': ('Scope the need',
        'Design the workflow',
        'Develop the agreed scope',
        'Test and validate',
        'Prepare delivery')}

FORBIDDEN = (
    "siret",
    "siren",
    "immatricul",
    "certification",
    "certificat",
    "témoignage",
    "testimonial",
    "years of experience",
    "ans d'expérience",
    "ans d’expérience",
    "nos clients",
    "our clients",
    "notre équipe",
    "our team",
)


def _language_block(html: str, lang: str) -> str:
    match = re.search(rf"\n      {lang}:\{{(.*?)\n      \}}", html, re.S)
    assert match, f"missing {lang} translations"
    return match.group(1)


def _pairs(block: str) -> dict[str, str]:
    return dict(re.findall(r'\n        ([A-Za-z0-9]+):"((?:\\.|[^"\\])*)"', block))


def test_hero_service_and_approach_copy():
    html = read_text("index.html")
    for lang, hero in HERO.items():
        pairs = _pairs(_language_block(html, lang))
        for key, value in hero.items():
            assert pairs[key] == value
        for key, value in SERVICES[lang].items():
            assert pairs[key] == value
        titles = [pairs[f"step{index}Title"] for index in range(1, 6)]
        assert tuple(titles) == STEPS[lang]


def test_visible_french_matches_the_translation_table():
    html = read_text("index.html")
    french = _pairs(_language_block(html, "fr"))
    english = _pairs(_language_block(html, "en"))
    assert set(french) == set(english)
    seen = set()
    for key, text in re.findall(r'data-i18n="([^"]+)">([^<]*)<', html):
        assert french[key] == text, key
        seen.add(key)
    for key in re.findall(r'data-i18n-aria="([^"]+)"', html):
        assert key in french
        seen.add(key)
    for key in re.findall(r'data-i18n-alt="([^"]+)"', html):
        assert key in french
        seen.add(key)
    assert {"heroTitle", "ctaServices", "ctaProject", "service3Title", "step5Title", "aboutText"} <= seen


def test_calls_to_action_and_contact_channels():
    html = read_text("index.html")
    assert 'href="#projects" data-i18n="ctaServices"' in html
    assert 'href="#contact" data-i18n="ctaProject"' in html
    assert 'href="mailto:contact@mamourart.com"' in html
    assert '<form class="quote-form"' in html
    assert 'action="contact-submit.php"' in html
    assert "Les demandes ne sont pas stockées dans une base de données du site." in html


def test_about_presents_a_brand_without_invented_credentials():
    html = read_text("index.html")
    french = _pairs(_language_block(html, "fr"))
    english = _pairs(_language_block(html, "en"))
    assert "marque" in french["aboutText"]
    assert "studio" in french["aboutText"]
    assert "brand" in english["aboutText"]
    assert "studio" in english["aboutText"]
    lowered = html.lower()
    for marker in FORBIDDEN:
        assert marker not in lowered, marker


def test_mobile_navigation_and_document_outline():
    html = read_text("index.html")
    page = parse_page(html)
    assert 'id="menuToggle"' in html
    assert 'aria-controls="navLinks"' in html
    assert 'rel="canonical" href="https://mamourart.com/"' in html
    assert 'rel="manifest" href="manifest.json"' in html
    assert html.lower().count("<h1") == 1
    assert {"top", "services", "projects", "approach", "about", "contact"} <= set(page.ids)
    assert ">Android<" in html
    assert "Androïd" not in html
