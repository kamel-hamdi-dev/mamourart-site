"""Mission 44: real first visits, image failures, Cache Storage and byte counts.

python tests/browser_mission44.py --output /tmp/mission44-validation
All content is served by a loopback fixture. No PHP or POST is permitted.
The browser image decoder is real; unsupported WebP is explicitly simulated by
changing only its source MIME. Disabling CSS image-set never removes preloads.
"""
import argparse
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_mission42 import FixtureServer, ROOT, install, settle_hero


Fixture44 = FixtureServer


def new_page(browser, fixture, width=390):
    # Request interception disables Chromium's HTTP cache. Observe instead so
    # transfer measurements include normal HTTP-cache reuse by the SW install.
    context = browser.new_context(viewport={"width": width, "height": 1000})
    page = context.new_page()
    page.set_default_timeout(20000)
    page.add_init_script("window.initiallyControlled = !!navigator.serviceWorker.controller")
    unexpected, errors = [], []
    page.on("request", lambda request: unexpected.append(request.url)
            if not request.url.startswith(fixture.origin + "/") or request.method != "GET" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    return context, page, unexpected, errors


def banner_state(page):
    return page.locator("#heroBanner").evaluate("""async image => {
      await Promise.race([image.decode(), new Promise((_, reject) => setTimeout(() => reject(Error("banner decode timeout")), 20000))]);
      const style = getComputedStyle(image);
      return {src:new URL(image.currentSrc).pathname, width:image.naturalWidth,
        height:image.naturalHeight, fit:style.objectFit, position:style.objectPosition};
    }""")


def cache_snapshot(page, cache="mamourart-v9"):
    return page.evaluate("""async name => {
      if (!(await caches.has(name))) return null;
      const cache = await caches.open(name), entries = {};
      for (const key of await cache.keys()) {
        const response = await cache.match(key), body = await response.arrayBuffer();
        const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', body))]
          .map(b => b.toString(16).padStart(2,'0')).join('');
        entries[new URL(key.url).pathname] = {bytes:body.byteLength, hash, mime:response.headers.get('Content-Type')};
      }
      return entries;
    }""", cache)


def first_visits(browser, report, output):
    for scenario in ("normal", "unsupported-webp", "webp-404", "webp-invalid", "no-image-set"):
        for width in (320, 390, 768, 1440):
            for name in ("index.html", "en.html"):
                fallback = scenario if scenario in ("unsupported-webp", "no-image-set") else None
                fixture = Fixture44(scenario="normal" if fallback else scenario, fallback=fallback)
                context, page, unexpected, errors = new_page(browser, fixture, width)
                try:
                    print(f"RUN {scenario} {width} {name}", flush=True)
                    page.goto(fixture.origin + "/" + name)
                    assert not page.evaluate("window.initiallyControlled"), "must start without an active worker"
                    assert page.evaluate("Promise.race([window.mamourartOfflineReady, new Promise((_,reject) => setTimeout(() => reject(Error('offline readiness timeout')), 20000))])"), (scenario, name)
                    state = banner_state(page)
                    selected = "png" if scenario in ("unsupported-webp", "webp-404", "webp-invalid") else "webp"
                    assert state["src"] == "/banner." + selected, (scenario, state)
                    assert (state["width"], state["height"], state["fit"]) == (2560, 1440, "cover")
                    assert state["position"] == ("72% 50%" if width <= 760 else "100% 50%"), state
                    cache_name = "mamourart-v9-png-logo-png" if scenario == "unsupported-webp" else "mamourart-v9-png" if selected == "png" else "mamourart-v9"
                    snapshot = cache_snapshot(page, cache_name)
                    if scenario == "unsupported-webp":
                        assert "/logo.png" in snapshot and "/logo.webp" not in snapshot
                        assert not any(t["path"] == "/logo.webp" for t in fixture.transfers)
                    expected = (ROOT / ("banner." + selected)).read_bytes()
                    assert snapshot[state["src"]]["hash"] == hashlib.sha256(expected).hexdigest()
                    assert "/banner." + ("webp" if selected == "png" else "png") not in snapshot
                    transfers = [t for t in fixture.transfers if t["path"].startswith("/banner.")]
                    if scenario in ("normal", "no-image-set"):
                        assert transfers == [{"path": "/banner.webp", "status": 200, "bytes": 76404}], transfers
                    if scenario == "unsupported-webp":
                        assert transfers == [{"path": "/banner.png", "status": 200, "bytes": 953545}], transfers
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    # Clear the HTTP cache before offline reload: Cache Storage
                    # alone must provide every essential document and banner.
                    cdp = context.new_cdp_session(page)
                    cdp.send("Network.clearBrowserCache")
                    context.set_offline(True)
                    assert page.reload().status == 200
                    offline = banner_state(page)
                    assert offline["src"] == state["src"] and offline["width"] == 2560, (scenario, offline)
                    if name == "en.html":
                        assert page.locator("html").get_attribute("lang") == "en"
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    if scenario in ("normal", "webp-invalid") and width in (320, 1440):
                        settle_hero(page)
                        page.screenshot(path=str(output / f"{scenario}-{name}-{width}.png"))
                    context.set_offline(False)
                    assert page.reload().status == 200
                    assert banner_state(page)["width"] == 2560
                    assert not errors and not unexpected, (errors, unexpected)
                    report["first_visits"].append({"scenario": scenario, "page": name, "width": width,
                        "uncontrolled_start": True, "selected": state, "cache": cache_name,
                        "banner_transfers": transfers, "offline_without_http_cache": True, "reonline": True})
                finally:
                    context.close()
                    fixture.close()
    print(f"PASS {len(report['first_visits'])} first-visit FR/EN/viewport cases, explicit WebP failures and offline decode", flush=True)


def rejected_updates(browser, report):
    for scenario in ("empty-body", "wrong-mime", "invalid-html", "invalid-utf8", "truncated-stream",
                     "invalid-json", "invalid-manifest", "image-invalid", "storage-cleanup-failure", "storage-total-failure"):
        print(f"RUN update {scenario}", flush=True)
        fixture = Fixture44(version="audited")
        context, page, unexpected, errors = new_page(browser, fixture)
        try:
            assert install(page, fixture)["state"] == "activated"
            previous = cache_snapshot(page, "mamourart-v7")
            assert previous and len(previous) == 12
            fixture.version, fixture.scenario = "fixed", scenario
            outcome = install(page, fixture, update=True)
            assert outcome["state"] == "redundant", (scenario, outcome)
            assert cache_snapshot(page, "mamourart-v7") == previous
            candidate = cache_snapshot(page)
            if scenario == "storage-total-failure":
                assert candidate and len(candidate) == 1
                for path, entry in candidate.items():
                    name = path.lstrip('/') or 'index.html'
                    assert entry['hash'] == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            elif scenario == "storage-cleanup-failure":
                assert candidate == {}, candidate
            else:
                assert candidate is None
            context.set_offline(True)
            assert page.goto(fixture.origin + "/legal.html").status == 200
            assert "Mentions" in page.content()
            assert not errors and not unexpected, (errors, unexpected)
            if scenario == "storage-total-failure":
                # A later valid worker must remove even unexpected stale entries.
                context.set_offline(False)
                page.evaluate("async () => {const c = await caches.open('mamourart-v9'); await c.put('/unexpected-residue', new Response('stale'));}")
                fixture.scenario = "normal"
                recovered = install(page, fixture, update=True)
                assert recovered["state"] == "activated", recovered
                fresh = cache_snapshot(page)
                assert fresh and len(fresh) == 12 and "/unexpected-residue" not in fresh
                assert cache_snapshot(page, "mamourart-v7") is None
                context.set_offline(True)
                assert page.goto(fixture.origin + "/en.html").status == 200
                report["residue_recovery"] = {"activated": True, "entries": len(fresh), "offline_en": True}
            report["rejected_updates"].append({"scenario": scenario, "outcome": outcome,
                "v7_unchanged": True, "candidate_entries": len(candidate or {}), "old_offline_document": True})
        finally:
            context.close()
            fixture.close()
    print(f"PASS {len(report['rejected_updates'])} invalid-content updates with real Cache Storage; v7 unchanged", flush=True)


def runtime_rejection(browser, report):
    fixture = Fixture44()
    context, page, unexpected, errors = new_page(browser, fixture)
    try:
        assert install(page, fixture)["state"] == "activated"
        previous = cache_snapshot(page)
        for scenario in ("empty-body", "wrong-mime", "invalid-html", "invalid-utf8", "truncated-stream",
                         "invalid-json", "invalid-manifest", "image-invalid"):
            fixture.scenario = scenario
            target = "/manifest.json" if scenario.startswith("invalid-") and scenario in ("invalid-json", "invalid-manifest") else "/icon-192.png" if scenario == "image-invalid" else "/legal.html"
            page.evaluate("async path => {try {await (await fetch(path)).arrayBuffer();} catch (_) {}}", target)
            assert cache_snapshot(page) == previous, scenario
            report["runtime_rejection"].append({"scenario": scenario, "cache_unchanged": True})
        context.set_offline(True)
        assert page.goto(fixture.origin + "/legal.html").status == 200
        assert not errors and not unexpected, (errors, unexpected)
    finally:
        context.close()
        fixture.close()
    print("PASS invalid runtime bodies never overwrite validated offline resources", flush=True)


def audited_reproductions(browser, report):
    for scenario in ("webp-404", "webp-invalid"):
        fixture = Fixture44(version="audited", scenario=scenario)
        context, page, unexpected, errors = new_page(browser, fixture)
        try:
            page.goto(fixture.origin + "/index.html")
            page.wait_for_load_state("networkidle")
            requests = [t for t in fixture.transfers if t["path"].startswith("/banner.")]
            assert not any(t["path"] == "/banner.png" for t in requests), requests
            report["audited_reproductions"].append({"scenario": scenario, "png_recovery": False, "transfers": requests})
        finally:
            context.close(); fixture.close()
    for scenario in ("normal", "no-image-set", "unsupported-webp"):
        fixture = Fixture44(version="audited", fallback=None if scenario == "normal" else scenario)
        context, page, unexpected, errors = new_page(browser, fixture)
        try:
            page.goto(fixture.origin + "/index.html")
            page.evaluate("navigator.serviceWorker.ready.then(() => true)")
            transfers = [t for t in fixture.transfers if t["path"].startswith("/banner.")]
            if scenario == "no-image-set":
                assert {t["path"] for t in transfers} == {"/banner.webp", "/banner.png"}, transfers
                assert page.locator('link[rel=preload][href="banner.webp"]').count() == 1
            if scenario == "unsupported-webp":
                assert "/banner.png" not in cache_snapshot(page, "mamourart-v7")
                context.new_cdp_session(page).send("Network.clearBrowserCache")
                context.set_offline(True)
                page.reload()
                loaded = page.evaluate("""async () => {const image=new Image(); image.src='/banner.png';
                  try {await image.decode(); return true;} catch (_) {return false;}}""")
                assert not loaded
            report["audited_reproductions"].append({"scenario": scenario, "transfers": transfers,
                "bytes": sum(t["bytes"] for t in transfers), "png_in_cache": "/banner.png" in (cache_snapshot(page, "mamourart-v7") or {})})
        finally:
            context.close(); fixture.close()
    print("PASS audited-SHA reproductions: broken WebP, first-visit PNG offline miss, independent image-set/preload double transfer", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/mission44-validation"))
    parser.add_argument("--only", choices=["audit", "updates", "runtime", "first"])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {key: [] for key in ("audited_reproductions", "first_visits", "rejected_updates", "runtime_rejection")}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/chromium", headless=True,
            args=["--no-sandbox", "--disable-background-networking", "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"])
        try:
            if args.only in (None, "audit"): audited_reproductions(browser, report)
            if args.only in (None, "updates"): rejected_updates(browser, report)
            if args.only in (None, "runtime"): runtime_rejection(browser, report)
            if args.only in (None, "first"): first_visits(browser, report, args.output)
        finally:
            browser.close()
            (args.output / ("chromium44-" + args.only + ".json" if args.only else "chromium44.json")).write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
