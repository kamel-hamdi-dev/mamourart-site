# Mission 24: bilingual legal/privacy static checks.
from tests.checks import read_text


def test_legal_page_bilingual_details():
    page = read_text("legal.html")
    assert 'data-legal-lang="fr"' in page
    assert 'data-legal-lang="en"' in page
    assert 'id="legal-fr"' in page and 'id="legal-en"' in page
    assert 'id="privacy-fr"' in page and 'id="privacy-en"' in page
    for item in ("Kamel Hamdi", "28 avenue des Pépinières", "94260 Fresnes",
                 "contact@mamourart.com", "07 62 22 95 32",
                 "OVH SAS", "2 rue Kellermann", "59100 Roubaix", "CNIL"):
        assert item in page
    assert "12 mois après le dernier échange" in page
    assert "12 months after the last exchange" in page
    assert "l'intérêt légitime" in page
    assert "legitimate interests" in page


def test_homepage_links_legal_privacy_both_languages():
    page = read_text("index.html")
    assert page.count('data-legal-link="privacy"') == 2
    assert page.count('data-legal-link="legal"') == 1
    assert 'href="legal.html?lang=fr#privacy-fr"' in page
    assert 'href="legal.html?lang=fr#legal-fr"' in page
    assert 'querySelectorAll("[data-legal-link]")' in page
    for label in ("quotePolicyLink", "legalNotices", "privacyPolicy"):
        assert page.count(label + ':"') == 2
    assert "12 mois après le dernier échange" in page
    assert "12 months after the last exchange" in page


def test_php_redirect_returns_to_private_test_if_present():
    php = read_text("contact-submit.php")
    assert "is_file(__DIR__ . '/mamourart-form-test.html')" in php
    assert "'/?contact_status='" in php
    assert "'mamourart-form-test.html?contact_status='" in php
    assert "filter_var($email, FILTER_VALIDATE_EMAIL)" in php
