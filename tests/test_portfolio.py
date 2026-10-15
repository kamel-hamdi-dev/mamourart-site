"""Portfolio entry for Mamourart Mes Heures, still in preparation."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from tests.checks import ROOT, read_text

HOURS_COPY = {
    "fr": {
        "hoursStatus": "En préparation",
        "hoursText": (
            "Application Android de suivi des heures de travail, des plannings "
            "et d'estimation du salaire, destinée aux salariés en France."
        ),
        "hoursFeatures": (
            "Fonctionnalités prévues : suivi des heures, planning, estimation du salaire "
            "et module d'information « Mes droits »."
        ),
        "hoursNote": "Pas encore publié",
    },
    "en": {
        "hoursStatus": "In preparation",
        "hoursText": (
            "Android application for tracking working hours, schedules and estimated pay, "
            "designed for employees in France."
        ),
        "hoursFeatures": (
            "Planned features: time tracking, work schedules, pay estimates "
            "and a worker rights information module."
        ),
        "hoursNote": "Not yet published",
    },
}


def _articles(html: str) -> list[str]:
    return re.findall(r"<article class=\"project-card(?: featured)?\">(.*?)</article>", html, re.S)


def _hours_card(html: str) -> str:
    matches = [article for article in _articles(html) if "Mamourart Mes Heures" in article]
    assert len(matches) == 1
    return matches[0]


def _language_block(html: str, lang: str) -> str:
    match = re.search(rf"\n      {lang}:\{{(.*?)\n      \}}", html, re.S)
    assert match, f"missing {lang} translations"
    return match.group(1)


def test_existing_portfolio_projects_remain():
    titles = [re.search(r"<h3>(.*?)</h3>", article).group(1) for article in _articles(read_text("index.html"))]
    assert titles == [
        "Mamourart Transport Automation",
        "Mamourart GPS AI",
        "Mamourart Desktop Agent",
        "Mamourart Website",
        "Mamourart Mes Heures",
    ]


def test_mes_heures_is_in_preparation_without_a_download():
    card = _hours_card(read_text("index.html"))
    assert 'class="status prep"' in card
    assert ">En préparation<" in card
    assert ">Android<" in card
    assert "Fonctionnalités prévues" in card
    assert "« Mes droits »" in card
    assert "<a " not in card
    assert "<img " not in card
    assert "http" not in card
    lowered = card.lower()
    for marker in ("télécharger", "download", "play.google", "app store", "apk"):
        assert marker not in lowered


def test_mes_heures_copy_exists_in_french_and_english():
    html = read_text("index.html")
    for lang, copy in HOURS_COPY.items():
        block = _language_block(html, lang)
        for key, value in copy.items():
            assert f'{key}:"{value}"' in block


def test_logo_and_favicon_references_stay():
    html = read_text("index.html")
    assert '<img src="logo.png" alt="Mamourart">' in html
    assert '<link rel="icon" href="favicon.ico" sizes="any">' in html
    assert 'href="favicon-32x32.png"' in html
    assert 'href="apple-touch-icon.png"' in html
    for name in ("logo.png", "favicon.ico", "favicon-32x32.png", "apple-touch-icon.png"):
        assert (ROOT / name).is_file()
        assert (ROOT / name).stat().st_size > 0


def test_homepage_script_parses():
    node = shutil.which("node")
    assert node, "node is required to syntax-check the homepage script"
    html = read_text("index.html")
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert len(scripts) == 1
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "homepage.js"
        script.write_text(scripts[0], encoding="utf-8")
        result = subprocess.run([node, "--check", str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
