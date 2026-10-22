"""Local-only Chromium integration checks; run with Python + Playwright installed.

No request reaches PHP and no form is submitted. PHP redirect behavior is tested
separately by the isolated PHP suite; these checks verify the rendered result.
"""
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://mamourart-integration.test"
OUTPUT = Path("/tmp/mission40-validation")


def expected_result(lang, status):
    return {
        ("fr", "sent"): "Votre demande a été envoyée.",
        ("fr", "error"): "L'envoi n'a pas abouti.",
        ("en", "sent"): "Your request was sent.",
        ("en", "error"): "Your message could not be sent.",
    }[lang, status]


def assert_result(page, lang, status, focus=True):
    assert page.locator("html").get_attribute("lang") == lang
    result = page.locator("#quoteResult")
    assert result.inner_text().startswith(expected_result(lang, status))
    assert result.is_visible()
    # The document uses smooth scrolling; wait until the load handler's scroll
    # settles before assessing the confirmation's viewport position.
    page.wait_for_function("() => {const r=document.querySelector('#quoteResult').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight}", timeout=5000)
    if focus:
        assert result.evaluate("e => document.activeElement === e")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def assert_keyboard_form(page):
    page.locator("[name=name]").focus()
    for name in ("company", "email", "service", "details", "privacy_ack"):
        page.keyboard.press("Tab")
        assert page.locator(f"[name={name}]").evaluate("e => document.activeElement === e"), name
    assert not page.locator("[name=privacy_ack]").is_checked()
    page.keyboard.press("Space")
    assert page.locator("[name=privacy_ack]").is_checked()
    page.keyboard.press("Tab")
    assert page.locator("form [data-legal-link=privacy]").evaluate("e => document.activeElement === e")
    page.keyboard.press("Tab")
    assert page.locator("form button[type=submit]").evaluate("e => document.activeElement === e")
    assert page.locator("[name=website]").get_attribute("tabindex") == "-1"
    assert page.locator("[name=website]").input_value() == ""
    for name, value in {"name": "Local Test", "company": "Fictional business", "email": "local@example.invalid", "details": "A fictional project for an isolated browser check."}.items():
        page.locator(f"[name={name}]").fill(value)
    page.locator("[name=service]").select_option("software")
    assert page.locator("form").evaluate("e => e.checkValidity()")
    page.locator("[name=privacy_ack]").uncheck()
    assert not page.locator("form").evaluate("e => e.checkValidity()")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    totals = {"result_matrix": 0, "language_and_back_cycles": 0, "keyboard_forms": 0, "legacy_urls": 0}
    unexpected = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="/usr/bin/chromium", headless=True,
            args=["--no-sandbox", "--disable-background-networking", "--host-resolver-rules=MAP * ~NOTFOUND"],
        )
        for width in (320, 390, 768, 1440):
            for blocked in (False, True):
                for name, lang in (("index.html", "fr"), ("en.html", "en")):
                    context = browser.new_context(service_workers="block", viewport={"width": width, "height": 900})

                    def route(request):
                        url = urlsplit(request.request.url)
                        if url.netloc != "mamourart-integration.test" or request.request.method != "GET" or url.path.endswith(".php"):
                            unexpected.append(request.request.url)
                            request.abort()
                            return
                        path = (ROOT / (url.path.lstrip("/") or "index.html")).resolve()
                        if path.is_relative_to(ROOT) and path.is_file():
                            request.fulfill(path=str(path))
                        else:
                            request.fulfill(status=404, body="missing local fixture")

                    context.route("**/*", route)
                    if blocked:
                        context.add_init_script("Object.defineProperty(window, 'localStorage', {get(){throw new DOMException('disabled', 'SecurityError')}})")
                    else:
                        # Deliberately oppose the static page, including stale EN on FR.
                        stale = "en" if lang == "fr" else "fr"
                        context.add_init_script(f"localStorage.setItem('mamourart-language-v2', '{stale}')")
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    for status in ("sent", "error"):
                        target = f"{ORIGIN}/{name}?contact_status={status}#quoteResult"
                        page.goto(target)
                        assert_result(page, lang, status)
                        assert page.locator("[name=name]").get_attribute("minlength") == "2"
                        assert page.locator("form").get_attribute("action") == "contact-submit.php" + ("?lang=en" if lang == "en" else "")
                        totals["result_matrix"] += 1
                        other = "en" if lang == "fr" else "fr"
                        page.locator(f"#{other}Button").click()
                        expected_path = "/en.html" if other == "en" else "/"
                        page.wait_for_url(f"{ORIGIN}{expected_path}?contact_status={status}#quoteResult")
                        assert_result(page, other, status)
                        page.go_back()
                        page.wait_for_url(target)
                        # Back restores browser history; focus is checked on initial load.
                        assert_result(page, lang, status, focus=False)
                        totals["language_and_back_cycles"] += 1
                    assert_keyboard_form(page)
                    totals["keyboard_forms"] += 1
                    if lang == "fr":
                        page.goto(f"{ORIGIN}/?contact_status=sent#quoteResult")
                        assert_result(page, "fr", "sent")
                        page.goto(f"{ORIGIN}/index.html?contact_status=error#quoteResult")
                        assert_result(page, "fr", "error")
                        totals["legacy_urls"] += 2
                    if (width, lang, blocked) in ((1440, "fr", False), (390, "en", True)):
                        page.goto(f"{ORIGIN}/{name}")
                        page.screenshot(path=str(OUTPUT / f"homepage-{lang}-{width}.png"), full_page=True)
                        page.goto(f"{ORIGIN}/{name}?contact_status=sent#quoteResult")
                        assert_result(page, lang, "sent")
                        page.screenshot(path=str(OUTPUT / f"confirmation-{lang}-{width}.png"))
                    assert not errors, errors
                    context.close()
        assert not unexpected, unexpected
        browser.close()
    print("PASS Chromium Mission 40:", totals)
    print("All requests intercepted from local files; service workers blocked in this harness; no PHP request, submission, external request or mail.")


if __name__ == "__main__":
    main()
