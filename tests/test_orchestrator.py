"""Bilingual concept presentation, local-only demo and public-file contracts."""
import json
import re
import secrets
import subprocess
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urlparse

import pytest

from tests.checks import ROOT, parse_page, read_text, site_file

PAGES = {"fr": "ai-agent-orchestrator.html", "en": "ai-agent-orchestrator-en.html"}


class PresentationContract(HTMLParser):
    """Structural allowlist for these static presentations, not an HTML sanitizer."""
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.scripts = []
        self.in_script = False
        self.feed(html)
        assert len(self.scripts) == 1, "Exactly one reviewed inline script"

    def handle_starttag(self, tag, pairs):
        attributes = dict(pairs)
        assert len(attributes) == len(pairs), "Duplicate HTML attributes"
        assert tag not in {"form", "iframe", "object", "embed", "base", "foreignobject"}, "Active embedded content"
        assert not any(key.startswith("on") for key in attributes), "Inline event handler"
        assert "srcdoc" not in attributes and "ping" not in attributes, "Unreviewed execution or IO"
        # These reviewed documents use style blocks only. Rejecting inline CSS
        # also closes entity/escape variations of remote CSS resource loads.
        assert "style" not in attributes, "Unreviewed inline CSS attribute"
        if tag == "meta":
            assert (attributes.get("http-equiv") or "").strip().casefold() != "refresh", "Meta refresh redirect"
        for key in {"fill", "stroke", "filter", "clip-path", "mask", "cursor", "background",
                    "marker-start", "marker-mid", "marker-end"} & attributes.keys():
            value = attributes[key] or ""
            assert not re.search(r"url\s*\(|@\s*import|\\", value, re.I), "Unreviewed CSS presentation resource"
        if tag == "script":
            assert not attributes, "External or unreviewed script attributes"
            self.scripts.append("")
            self.in_script = True
        for key in ("href", "xlink:href", "src", "data", "action", "formaction", "poster"):
            if key not in attributes:
                continue
            value = attributes[key] or ""
            url = urlparse(value)
            if tag == "link" and attributes.get("rel") in {"canonical", "alternate"}:
                assert url.scheme == "https" and url.netloc == "mamourart.com"
            else:
                assert value and not url.scheme and not url.netloc and not value.startswith("//"), "Non-local resource or active URL"
                assert ".." not in url.path.split("/"), "Path traversal"
        assert "srcset" not in attributes, "Unreviewed alternate resources"

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.scripts[-1] += data


def reviewed_script(html):
    contract = PresentationContract(html)
    # Also reject CSS resource loads; these pages require no external stylesheet.
    for css in re.findall(r"<style[^>]*>(.*?)</style>", html, re.I | re.S):
        assert not re.search(r"@\s*import\b|url\s*\(", css, re.I), "Unreviewed CSS resource"
    return contract.scripts[0]


def run_runtime(script, lang, scenario, tmp_path):
    path = tmp_path / "presentation.js"
    path.write_text(script)
    run_id = secrets.token_hex(16)
    result = subprocess.run(["node", str(ROOT / "tests/orchestrator_runtime.cjs"), str(path), lang, scenario, run_id],
                            capture_output=True, text=True, timeout=10)
    result.runtime_run_id = run_id
    return result


def assert_runtime_success(result, lang, scenario):
    assert result.returncode == 0, result.stdout + result.stderr
    prefix = "ORCHESTRATOR_RUNTIME_COMPLETE "
    markers = [line[len(prefix):] for line in result.stdout.splitlines() if line.startswith(prefix)]
    assert len(markers) == 1, "Missing or duplicate runtime completion marker"
    assert json.loads(markers[0]) == {
        "version": 1, "runId": result.runtime_run_id, "language": lang,
        "scenario": scenario, "decisionsVerified": 5, "assertionsComplete": True,
    }, "Incomplete or mismatched runtime completion marker"


@pytest.mark.parametrize("lang", PAGES)
def test_concept_status_and_required_topics(lang):
    html = read_text(PAGES[lang])
    page = parse_page(html)
    assert page.language == lang
    assert html.count("<h1>") == 1
    assert len(page.ids) == len(set(page.ids))
    for topic in ("Cloud", "Cloud + Windows", "GO", "NO-GO", "GitHub"):
        assert topic in html
    for topic in ({"fr": ("En conception", "fictives", "Superviseur IA", "journal", "pas un logiciel développé ou commercialisé", "Absence de réponse ≠ accord"),
                   "en": ("In design", "fictional data", "AI supervisor", "log", "not developed or marketed software", "No response ≠ approval")}[lang]):
        assert topic in html
    assert "<form" not in html
    assert 'role="status" aria-live="polite"' in html
    assert 'href="#main"' in html
    assert "prefers-reduced-motion:reduce" in html


@pytest.mark.parametrize("lang", PAGES)
def test_seo_and_links_resolve(lang):
    html = read_text(PAGES[lang])
    page = parse_page(html)
    assert page.meta_content["description"]
    assert f'rel="canonical" href="https://mamourart.com/{PAGES[lang]}"' in html
    for code, name in PAGES.items():
        assert f'hreflang="{code}" href="https://mamourart.com/{name}"' in html
    assert 'rel="manifest" href="manifest.json"' in html
    for anchor in page.anchors:
        url = urlparse(anchor["href"])
        assert not url.scheme and not url.netloc, anchor
        target = site_file(url.path or PAGES[lang])
        assert target.is_file(), anchor
        if url.fragment:
            assert url.fragment in parse_page(target.read_text()).ids, anchor


@pytest.mark.parametrize("lang", PAGES)
@pytest.mark.parametrize("scenario", ["webp", "png", "bitmap-png", "no-worker", "broken-images"])
def test_simulation_script_has_no_operational_io(lang, scenario, tmp_path):
    html = read_text(PAGES[lang])
    script = reviewed_script(html)
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert len(scripts) == 1
    assert script == scripts[0]
    # Retain the earlier string checks as additional guards, alongside structural
    # parsing and the executable behavior contract (including spaced API calls).
    for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "localStorage", "sessionStorage", "innerHTML", "eval("):
        assert forbidden not in script
    assert not re.search(r"location\.href\s*=", script)
    assert "textContent = messages[button.dataset.decision]" in script
    path = tmp_path / "demo.js"
    path.write_text(script)
    result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = run_runtime(script, lang, scenario, tmp_path)
    assert_runtime_success(result, lang, scenario)


@pytest.mark.parametrize("injection", [
    '<script src="https://example.invalid/probe.js"></script>',
    '<ScRiPt SRC = "/unreviewed.js"></ScRiPt>',
    '<script type="module" src="//example.invalid/probe.js"></script>',
    '<script>fetch ("https://example.invalid/probe")</script>',
    '<img src="/logo.png" onerror="alert(1)">',
    '<img src="https://example.invalid/tracker.png">',
    '<a href="javascript:alert(1)">probe</a>',
    '<iframe srcdoc="probe"></iframe>',
    '<style>@import "https://example.invalid/probe.css";</style>',
])
@pytest.mark.parametrize("lang", PAGES)
def test_html_contract_rejects_injected_active_content(lang, injection):
    with pytest.raises(AssertionError):
        reviewed_script(read_text(PAGES[lang]).replace("</body>", injection + "</body>"))


@pytest.mark.parametrize("lang", PAGES)
@pytest.mark.parametrize("injection,reason", [
    ('<div style="background-image:url(https://example.invalid/probe.png)"></div>', "Unreviewed inline CSS attribute"),
    ('<div STYLE="background:url(&#104;ttps://example.invalid/probe.png)"></div>', "Unreviewed inline CSS attribute"),
    (r'<div style="background:u\72l(https://example.invalid/probe.png)"></div>', "Unreviewed inline CSS attribute"),
    ('<svg><rect fill="url(https://example.invalid/probe.svg#fill)"></rect></svg>', "Unreviewed CSS presentation resource"),
    (r'<svg><rect fill="u\72l(https://example.invalid/probe.svg#fill)"></rect></svg>', "Unreviewed CSS presentation resource"),
    ('<meta http-equiv="refresh" content="0;url=https://example.invalid/probe">', "Meta refresh redirect"),
    ('<META HTTP-EQUIV=" ReFrEsH " CONTENT="0; URL=//example.invalid/probe"/>', "Meta refresh redirect"),
])
def test_html_rejects_css_attributes_and_meta_refresh(lang, injection, reason):
    with pytest.raises(AssertionError, match=reason):
        reviewed_script(read_text(PAGES[lang]).replace("</body>", injection + "</body>"))


@pytest.mark.parametrize("lang", PAGES)
@pytest.mark.parametrize("fault", ["caught-fetch", "caught-async-fetch", "caught-window-fetch", "caught-xhr", "caught-beacon"])
def test_runtime_records_forbidden_calls_even_when_caught(lang, fault, tmp_path):
    script = reviewed_script(read_text(PAGES[lang]))
    api = {"caught-window-fetch": "window.fetch ('https://example.invalid/probe')",
           "caught-xhr": "new XMLHttpRequest()", "caught-beacon": "navigator.sendBeacon('https://example.invalid/probe')"}.get(fault, "fetch ('https://example.invalid/probe')")
    old = "button.addEventListener('click', () => {"
    body = f"try {{ {api}; }} catch (_) {{}}"
    new = "button.addEventListener('click', async () => { await Promise.resolve(); " + body if fault == "caught-async-fetch" else old + " " + body
    mutant = script.replace(old, new)
    assert mutant != script
    result = run_runtime(mutant, lang, "webp", tmp_path)
    assert result.returncode != 0, result.stdout
    assert "Forbidden operational API attempts:" in result.stderr, result.stderr
    assert "ORCHESTRATOR_RUNTIME_COMPLETE " not in result.stdout


@pytest.mark.parametrize("lang", PAGES)
def test_runtime_rejects_unresolved_async_completion(lang, tmp_path):
    script = reviewed_script(read_text(PAGES[lang]))
    mutant = script + "\nwindow.mamourartOfflineReady = new Promise(() => {});"
    result = run_runtime(mutant, lang, "webp", tmp_path)
    assert result.returncode != 0, "An unresolved Promise must never count as success"
    assert "Runtime assertions did not complete" in result.stderr, result.stderr
    assert "ORCHESTRATOR_RUNTIME_COMPLETE " not in result.stdout


@pytest.mark.parametrize("fault", ["zero-exit", "pass-only", "incomplete-marker", "wrong-run-marker", "duplicate-marker"])
def test_parent_rejects_zero_exit_without_complete_async_proof(fault):
    run_id = "a" * 32
    marker = {"version": 1, "runId": run_id, "language": "fr", "scenario": "webp",
              "decisionsVerified": 5, "assertionsComplete": True}
    output = ""
    if fault == "pass-only":
        output = "PASS runtime fr webp\n"
    elif fault.endswith("marker"):
        if fault == "incomplete-marker":
            marker["decisionsVerified"] = 4
        elif fault == "wrong-run-marker":
            marker["runId"] = "b" * 32
        output = "ORCHESTRATOR_RUNTIME_COMPLETE " + json.dumps(marker) + "\n"
        if fault == "duplicate-marker":
            output *= 2
    # Real Node subprocess: exit code 0 alone, or a bare PASS log, is insufficient.
    result = subprocess.run(["node", "-e", "process.stdout.write(" + json.dumps(output) + "); process.exit(0);"],
                            capture_output=True, text=True, timeout=5)
    result.runtime_run_id = run_id
    assert result.returncode == 0
    with pytest.raises(AssertionError, match="runtime completion marker"):
        assert_runtime_success(result, "fr", "webp")


NETWORK_ANNOTATIONS = {"fr": "TOPOLOGIE CONCEPTUELLE · CONTRÔLE HUMAIN",
                       "en": "CONCEPT TOPOLOGY · HUMAN OVERSIGHT"}
NETWORK_KEY = "orchestratorNetworkAnnotation"


class NetworkAnnotation(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.annotations = []
        self.inside = False
        self.feed(html)

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if tag == "p" and "network-annotation" in attrs.get("class", "").split():
            self.annotations.append({"attrs": attrs, "text": ""})
            self.inside = True

    def handle_data(self, data):
        if self.inside:
            self.annotations[-1]["text"] += data

    def handle_endtag(self, tag):
        if tag == "p":
            self.inside = False


def assert_home_network_annotation(html, lang):
    parsed = NetworkAnnotation(html)
    assert len(parsed.annotations) == 1
    annotation = parsed.annotations[0]
    assert annotation["attrs"].get("data-i18n") == NETWORK_KEY, "Network annotation binding"
    assert annotation["text"].strip() == NETWORK_ANNOTATIONS[lang]
    for language, expected in NETWORK_ANNOTATIONS.items():
        block = re.search(rf"\n      {language}:\{{(.*?)\n      \}}", html, re.S)
        assert block
        value = re.search(rf'{NETWORK_KEY}:("[^"\n]*")', block.group(1))
        assert value and json.loads(value.group(1)) == expected, "Network annotation " + language + " translation"


@pytest.mark.parametrize("home,lang", [("index.html", "fr"), ("en.html", "en")])
def test_network_annotation_bindings_and_translations(home, lang):
    assert_home_network_annotation(read_text(home), lang)


@pytest.mark.parametrize("home,lang", [("index.html", "fr"), ("en.html", "en")])
def test_network_annotation_rejects_original_unsynced_markup(home, lang):
    html = read_text(home)
    mutant = html.replace(f' data-i18n="{NETWORK_KEY}"', "", 1)
    assert mutant != html
    with pytest.raises(AssertionError, match="Network annotation binding"):
        assert_home_network_annotation(mutant, lang)


@pytest.mark.parametrize("lang", PAGES)
@pytest.mark.parametrize("fault", ["wrong-go", "network-on-click", "forced-webp"])
def test_runtime_rejects_wrong_decision_and_operational_io(lang, fault, tmp_path):
    script = reviewed_script(read_text(PAGES[lang]))
    if fault == "wrong-go":
        mutant, count = re.subn(r'"go": "[^"]+"', '"go": "NO-GO M-03"', script, count=1)
        expected = "Exact go decision"
    elif fault == "network-on-click":
        mutant = script.replace("button.addEventListener('click', () => {", "button.addEventListener('click', () => { fetch ('https://example.invalid/probe');")
        count = int(mutant != script)
        expected = "Forbidden operational API: fetch"
    else:
        mutant = script.replace("navigator.serviceWorker.register(script)", "navigator.serviceWorker.register('/service-worker.js')")
        count = int(mutant != script)
        expected = "PWA installation readiness"
    assert count == 1, "Mutation must actually change the reviewed script"
    result = run_runtime(mutant, lang, "png" if fault == "forced-webp" else "webp", tmp_path)
    assert result.returncode != 0
    assert expected in result.stderr, result.stderr


@pytest.mark.parametrize("home", ["index.html", "en.html"])
def test_six_historical_cards_are_byte_identical_to_authorized_base(home):
    base = subprocess.check_output(["git", "show", "65c0be14db79355deb9153ad1e7de221254b40c1:" + home], cwd=ROOT, text=True)
    pattern = r'<article class="project-card(?: featured)?">.*?</article>'
    original = re.findall(pattern, base, re.S)
    current = re.findall(pattern, read_text(home), re.S)
    assert len(original) == 6
    assert current == original


def test_public_inventory_precache_and_sitemap_include_both_languages():
    inventory = json.loads(read_text("deploy-manifest.json"))["files"]
    worker = read_text("service-worker.js")
    sitemap = ET.fromstring(read_text("sitemap.xml"))
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9", "x": "http://www.w3.org/1999/xhtml"}
    for name in PAGES.values():
        assert inventory.count(name) == 1
        assert f'"/{name}"' in worker
        entries = [url for url in sitemap.findall("sm:url", ns) if url.find("sm:loc", ns).text == f"https://mamourart.com/{name}"]
        assert len(entries) == 1
        assert {link.attrib["hreflang"] for link in entries[0].findall("x:link", ns)} == {"fr", "en"}
    assert '"mamourart-v12"' in worker


@pytest.mark.parametrize("lang,home", [("fr", "index.html"), ("en", "en.html")])
def test_portfolio_card_is_localized_and_points_to_matching_page(lang, home):
    html = read_text(home)
    card = next(card for card in re.findall(r'<article class="project-card(?: featured)?(?: orchestrator-card)?">(.*?)</article>', html, re.S) if "Mamourart AI Agent Orchestrator" in card)
    assert f'href="{PAGES[lang]}"' in card
    assert ("En conception" if lang == "fr" else "In design") in card
    assert "data-orchestrator-link" in card
    for key in ("orchestratorStatus", "orchestratorText", "orchestratorNote", "orchestratorLink", "orchestratorTag"):
        assert f'data-i18n="{key}"' in card
        assert html.count(key + ':"') == 2
