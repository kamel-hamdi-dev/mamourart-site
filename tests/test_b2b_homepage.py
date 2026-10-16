"""Professional B2B homepage copy, in French and English."""

import re

from tests.checks import parse_page, read_text

HERO = {
    "fr": {
        "heroTitle": "Des logiciels sur mesure pour les entreprises.",
        "heroText": (
            "Mamourart conçoit des applications, automatise les processus métier "
            "et développe des solutions numériques adaptées aux besoins professionnels."
        ),
        "ctaServices": "Découvrir nos services",
        "ctaProject": "Discuter de votre projet",
    },
    "en": {
        "heroTitle": "Custom Software Solutions for Businesses.",
        "heroText": (
            "Mamourart designs applications, automates business processes "
            "and develops digital solutions tailored to professional needs."
        ),
        "ctaServices": "Explore our services",
        "ctaProject": "Discuss your project",
    },
}

SERVICES = {
    "fr": {
        "service1Title": "Développement logiciel sur mesure",
        "service1Text": "Applications métier, outils internes, solutions adaptées aux processus des entreprises.",
        "service2Title": "Développement web et mobile",
        "service2Text": "Sites professionnels, applications web et mobiles, interfaces responsive.",
        "service3Title": "Automatisation et intelligence artificielle",
        "service3Text": "Automatisation de tâches, intégration d'API, assistants et agents IA avec supervision humaine.",
        "service4Title": "Intégration de systèmes",
        "service4Text": "Connexion entre applications, bases de données, API et outils professionnels.",
    },
    "en": {
        "service1Title": "Custom Software Development",
        "service1Text": "Business applications, internal tools and solutions adapted to company processes.",
        "service2Title": "Web and Mobile Development",
        "service2Text": "Professional websites, web and mobile applications, responsive interfaces.",
        "service3Title": "Automation and Artificial Intelligence",
        "service3Text": "Task automation, API integration, AI assistants and agents with human supervision.",
        "service4Title": "Systems Integration",
        "service4Text": "Connections between applications, databases, APIs and professional tools.",
    },
}

STEPS = {
    "fr": (
        "Comprendre le besoin",
        "Définir la solution",
        "Concevoir et développer",
        "Tester et valider",
        "Livrer et accompagner",
    ),
    "en": (
        "Understand the need",
        "Define the solution",
        "Design and develop",
        "Test and validate",
        "Deliver and support",
    ),
}

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
    assert 'href="#services" data-i18n="ctaServices"' in html
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
