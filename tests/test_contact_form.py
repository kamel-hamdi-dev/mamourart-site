"""Mission 24: static checks for contact form; live mail delivery is checked separately."""
from pathlib import Path
from tests.checks import ROOT, read_text


def test_contact_form_is_bilingual_and_safe_by_default():
    html = read_text("index.html")
    assert 'action="contact-submit.php"' in html
    assert 'method="post"' in html
    for key in ("name", "company", "email", "service", "details", "privacy_ack", "website"):
        assert f'name="{key}"' in html
    assert 'type="email"' in html
    assert 'type="checkbox"' in html
    assert 'aria-live="polite"' in html
    for key in ("quoteTitle", "quoteName", "quoteService", "quoteDetails", "quoteSend", "quoteSuccess", "quoteError"):
        assert html.count(f'{key}:"') == 2
    php = (ROOT / "contact-submit.php").read_text(encoding="utf-8")
    assert "filter_var($email, FILTER_VALIDATE_EMAIL)" in php
    assert "HTTP_ORIGIN" in php
    assert "HTTP_SEC_FETCH_SITE" in php
    assert "require_once __DIR__ . '/contact-rate-limit.php'" in php
    assert "mamourart_contact_reserve(" in php
    limiter = (ROOT / "contact-rate-limit.php").read_text(encoding="utf-8")
    assert "flock(" in limiter
    assert "'Reply-To: ' . $email" in php
    assert "@mail('contact@mamourart.com'" in php
    assert "mail('contact@mamourart.com'," in php


def test_browser_limits_match_documented_utf16_server_limits():
    html = read_text("index.html")
    assert 'name="name" autocomplete="name" minlength="2" maxlength="120"' in html
    assert 'minlength="20" maxlength="3500"' in html
    php = read_text("contact-submit.php")
    assert "form_length($name)" in php
    assert "form_length($company)" in php
    assert "form_length($details)" in php
    assert "> 48000" in php


def test_ci_external_link_check_does_not_probe_production(monkeypatch):
    from urllib.parse import urlparse
    from tests import test_external_links

    requested = []
    def fake_status(url):
        requested.append(url)
        return 200

    monkeypatch.setattr(test_external_links, "_status", fake_status)
    test_external_links.test_external_links_respond()
    assert requested
    assert all(urlparse(url).hostname not in {"mamourart.com", "www.mamourart.com"}
               for url in requested)
