"""Mission 24: show a post-submit status without manually scrolling."""
from tests.checks import read_text


def test_php_redirects_to_visible_status_in_public_site():
    php = read_text("contact-submit.php")
    assert "'/?contact_status=' . $status . '#quoteResult'" in php
    assert "'mamourart-form-test.html?contact_status='" in php
    assert "back($ok ? 'sent' : 'error');" in php


def test_status_is_focusable_and_scrolls_after_load():
    html = read_text("index.html")
    assert 'id="quoteResult" role="status" aria-live="polite" tabindex="-1"' in html
    assert "scroll-margin-top:calc(var(--header) + 28px)" in html
    assert 'window.location.hash === "#quoteResult"' in html
    assert 'result.scrollIntoView({block: "center", behavior: "auto"});' in html
    assert 'result.focus({preventScroll: true});' in html
    assert 'submittedStatus === "sent" || submittedStatus === "error"' in html
