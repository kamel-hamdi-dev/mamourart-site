"""Local Chromium regressions for precache safety and responsive hero selection.

Run with Python + Playwright and /usr/bin/chromium. All HTTP is loopback and
synthetic; PHP/POST are refused. --baseline-only reproduces the audited v6 bugs.
Unsupported-image-format/support cases are explicit HTML/CSS simulations, not a
claim that Chromium itself lacks WebP or image-set support.
"""
import argparse
import json
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import Error, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("/tmp/mission42-validation")
BASELINE = "fade5c0a72867506d72c09019640233ba3d33e11"
PUBLIC = set(json.loads((ROOT / "deploy-manifest.json").read_text())["files"])
BASELINE_FILES = {
    name: subprocess.check_output(["git", "show", f"{BASELINE}:{name}"], cwd=ROOT)
    for name in PUBLIC
}


class FixtureServer:
    def __init__(self, version="fixed", scenario="normal", fallback=None):
        self.version = version
        self.scenario = scenario
        self.fallback = fallback
        self.requests = []
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.send_error(405)

            def do_GET(self):
                parsed = urlsplit(self.path)
                path = parsed.path
                fixture.requests.append(path)
                if path == "/harness.html":
                    return self.reply(200, b"<!doctype html><title>Local SW fixture</title><p>Local synthetic fixture</p>", "text/html")
                if path == "/redirect-target.html":
                    return self.reply(200, b"<!doctype html><title>Redirect target</title><p>SYNTHETIC REDIRECT</p>", "text/html")
                if path == "/legal.html" and fixture.scenario != "normal":
                    if fixture.scenario == "network":
                        self.close_connection = True
                        self.connection.close()
                        return
                    if fixture.scenario.startswith("status-"):
                        return self.reply(int(fixture.scenario.split("-")[1]), b"SYNTHETIC STATUS", "text/html")
                    if fixture.scenario == "redirect":
                        self.send_response(302)
                        self.send_header("Location", "/redirect-target.html")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    headers = {"Vary": "*"} if fixture.scenario == "vary" else {"Cache-Control": fixture.scenario}
                    return self.reply(200, b"<!doctype html><title>Private synthetic fixture</title><p>SYNTHETIC PRIVATE</p>", "text/html", headers)
                name = path.lstrip("/") or "index.html"
                if name not in PUBLIC or name.endswith(".php"):
                    return self.reply(404, b"missing local fixture", "text/plain")
                data = BASELINE_FILES[name] if fixture.version == "baseline" else (ROOT / name).read_bytes()
                if name in ("index.html", "en.html") and fixture.fallback:
                    html = data.decode()
                    if fixture.fallback == "unsupported-webp":
                        # MIME support drives real image-set/preload selection.
                        html = html.replace("image/webp", "image/x-mission42-unsupported")
                    elif fixture.fallback == "no-image-set":
                        # Keep the production fallback declarations verbatim.
                        html = re.sub(r'\s*background-image:[^;]*image-set\([^;]*;', '', html)
                        html = re.sub(r'<link[^>]+rel="preload"[^>]+href="banner.webp"[^>]*>', '', html)
                    data = html.encode()
                content_type = {
                    ".html": "text/html; charset=utf-8", ".js": "text/javascript",
                    ".json": "application/json", ".webp": "image/webp", ".png": "image/png",
                }.get(Path(name).suffix, "application/octet-stream")
                self.reply(200, data, content_type, {"Cache-Control": "no-store"} if name == "service-worker.js" else {})

            def reply(self, status, body, content_type, headers=None):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def context_for(browser, fixture, width=390, service_workers="allow"):
    context = browser.new_context(viewport={"width": width, "height": 1000}, service_workers=service_workers)
    unexpected = []

    def route(request):
        if request.request.url.startswith(fixture.origin + "/") and request.request.method == "GET":
            request.continue_()
        else:
            unexpected.append(request.request.url)
            request.abort()

    context.route("**/*", route)
    page = context.new_page()
    page.set_default_timeout(15000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    return context, page, errors, unexpected


def install(page, fixture, update=False):
    if not update:
        page.goto(fixture.origin + "/harness.html")
    return page.evaluate("""async update => {
      let registration = await navigator.serviceWorker.getRegistration();
      let worker;
      if (update) {
        const found = new Promise(resolve => registration.addEventListener('updatefound', () => resolve(registration.installing), {once:true}));
        await registration.update(); worker = registration.installing || await found;
      } else {
        registration = await navigator.serviceWorker.register('/service-worker.js');
        worker = registration.installing || registration.waiting || registration.active;
      }
      const state = await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(Error('Service worker state timeout')), 12000);
        const check = () => {if (['activated','redundant'].includes(worker.state)) {clearTimeout(timer); resolve(worker.state);}};
        worker.addEventListener('statechange', check); check();
      });
      return {state, active: registration.active !== null};
    }""", update)


def cached_legal(page, cache):
    return page.evaluate("""async cache => {
      if (!(await caches.has(cache))) return null;
      const response = await (await caches.open(cache)).match(location.origin + '/legal.html');
      return response ? {status:response.status, redirected:response.redirected,
        cacheControl:response.headers.get('Cache-Control'), vary:response.headers.get('Vary'),
        url:response.url, body:await response.text()} : null;
    }""", cache)


def settle_hero(page):
    # Capture the final design, rather than an intermediate opacity of enter.
    page.locator(".hero-inner").evaluate("async e => {await Promise.all(e.getAnimations({subtree:true}).map(animation => animation.finished));}")


def baseline_reproductions(browser, report):
    for scenario in ("no-store", "private", "redirect"):
        fixture = FixtureServer("baseline", scenario)
        context, page, errors, unexpected = context_for(browser, fixture)
        try:
            outcome = install(page, fixture)
            assert outcome["state"] == "activated", outcome
            cached = cached_legal(page, "mamourart-v6")
            assert cached and (cached["redirected"] if scenario == "redirect" else cached["cacheControl"] == scenario), cached
            record = {"scenario": scenario, "installed": True, "cached": cached}
            if scenario == "redirect":
                context.set_offline(True)
                try:
                    response = page.goto(fixture.origin + "/legal.html")
                    record["offline_status"] = response.status if response else None
                except Error as error:
                    record["offline_navigation_error"] = str(error).splitlines()[0]
                assert "ERR_FAILED" in record.get("offline_navigation_error", ""), record
            report["baseline_precache"].append(record)
            assert not errors and not unexpected, (errors, unexpected)
        finally:
            context.close()
            fixture.close()
    for width in (320, 390):
        for name in ("index.html", "en.html"):
            fixture = FixtureServer("baseline")
            context, page, errors, unexpected = context_for(browser, fixture, width, "block")
            try:
                page.goto(fixture.origin + "/" + name)
                banner = [path for path in fixture.requests if path.startswith("/banner.")]
                css = page.locator(".hero").evaluate("e => getComputedStyle(e).backgroundImage")
                assert "/banner.webp" in banner and "/banner.png" in banner, banner
                assert "banner.png?v=4" in css and "image-set" not in css, css
                report["baseline_banner"].append({"page": name, "width": width, "requests": banner,
                    "bytes": len(BASELINE_FILES["banner.webp"]) + len(BASELINE_FILES["banner.png"]), "css": css})
                assert not errors and not unexpected, (errors, unexpected)
            finally:
                context.close()
                fixture.close()
    print("PASS baseline Chromium reproduction: no-store/private/redirect cached by v6; offline redirect ERR_FAILED; FR/EN mobile PNG+WebP 1,029,949 bytes", flush=True)


def rejected_installs(browser, report):
    scenarios = ["no-store", "private", "vary", "redirect", "status-301", "status-302", "status-307", "status-308", "status-404", "status-500", "status-503", "network"]
    for scenario in scenarios:
        fixture = FixtureServer("fixed", scenario)
        context, page, errors, unexpected = context_for(browser, fixture)
        try:
            page.goto(fixture.origin + "/harness.html")
            page.evaluate("async () => {await (await caches.open('mamourart-v6')).put('/old-sentinel', new Response('old-valid')); await (await caches.open('other-app')).put('/sentinel', new Response('unrelated'));}")
            outcome = install(page, fixture)
            assert outcome == {"state": "redundant", "active": False}, (scenario, outcome)
            state = page.evaluate("async () => ({names:await caches.keys(), old:await (await (await caches.open('mamourart-v6')).match('/old-sentinel')).text(), third:await (await (await caches.open('other-app')).match('/sentinel')).text()})")
            assert "mamourart-v7" not in state["names"], (scenario, state)
            assert state["old"] == "old-valid" and state["third"] == "unrelated", state
            assert cached_legal(page, "mamourart-v7") is None
            report["rejected_installs"].append({"scenario": scenario, **outcome, **state})
            assert not errors and not unexpected, (scenario, errors, unexpected)
        finally:
            context.close()
            fixture.close()
    print(f"PASS {len(scenarios)} real Chromium unsafe/network install cases: v7 never activated/cached; old6 and third-party caches preserved", flush=True)


def update_and_offline(browser, report):
    for scenario in ("normal", "no-store", "private", "redirect"):
        fixture = FixtureServer("baseline")
        context, page, errors, unexpected = context_for(browser, fixture)
        try:
            assert install(page, fixture)["state"] == "activated"
            page.evaluate("async () => {await (await caches.open('other-app')).put('/sentinel', new Response('unrelated'));}")
            fixture.version = "fixed"
            fixture.scenario = scenario
            outcome = install(page, fixture, update=True)
            names = page.evaluate("caches.keys()")
            expected = "activated" if scenario == "normal" else "redundant"
            assert outcome["state"] == expected, (scenario, outcome)
            assert "other-app" in names
            assert ("mamourart-v7" in names) == (scenario == "normal"), (scenario, names)
            assert ("mamourart-v6" in names) == (scenario != "normal"), (scenario, names)
            if scenario != "normal":
                context.set_offline(True)
                response = page.goto(fixture.origin + "/legal.html")
                assert response.status == 200 and "SYNTHETIC" not in page.content()
            else:
                context.set_offline(True)
                for path in ("index.html", "en.html", "legal.html?lang=en", "gps-ai-demo.html?lang=en", "fret-alerts-demo.html?lang=en"):
                    response = page.goto(fixture.origin + "/" + path)
                    assert response.status == 200, (path, response.status)
                page.evaluate("caches.open('mamourart-v7').then(cache => cache.delete(location.origin + '/gps-ai-demo.html'))")
                response = page.goto(fixture.origin + "/gps-ai-demo.html?lang=en")
                assert response.status == 503 and "unavailable offline" in page.locator("h1").inner_text()
                context.set_offline(False)
                response = page.goto(fixture.origin + "/gps-ai-demo.html?lang=en")
                assert response.status == 200
            report["updates"].append({"scenario": scenario, "outcome": outcome, "caches": names})
            assert not errors and not unexpected, (scenario, errors, unexpected)
        finally:
            context.close()
            fixture.close()
    print("PASS v6 -> v7 safe update/offline503/reonline; three failed updates retain active v6 and its valid offline documents", flush=True)


def responsive_and_fallback(browser, report):
    for width in (320, 390, 768, 1440):
        for name in ("index.html", "en.html"):
            fixture = FixtureServer()
            context, page, errors, unexpected = context_for(browser, fixture, width, "block")
            try:
                bodies = []
                page.on("response", lambda response: bodies.append(response) if urlsplit(response.url).path.startswith("/banner.") else None)
                page.goto(fixture.origin + "/" + name)
                css = page.locator(".hero").evaluate("e => getComputedStyle(e).backgroundImage")
                requested = [path for path in fixture.requests if path.startswith("/banner.")]
                assert requested == ["/banner.webp"], (name, width, requested)
                assert "image-set" in css and "banner.webp" in css and "banner.png?v=" not in css, css
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                image = page.evaluate("""async () => {const i=new Image(); i.src='/banner.webp'; await i.decode(); return [i.naturalWidth,i.naturalHeight];}""")
                assert image == [2560, 1440], image
                size = sum(len(response.body()) for response in bodies)
                assert size == 76404, (name, width, size)
                settle_hero(page)
                page.screenshot(path=str(OUTPUT / f"hero-{name.split('.')[0]}-{width}.png"), full_page=False)
                report["responsive"].append({"page": name, "width": width, "requests": requested, "bytes": size, "css": css})
                assert not errors and not unexpected, (errors, unexpected)
            finally:
                context.close()
                fixture.close()
    for fallback in ("unsupported-webp", "no-image-set"):
        for name in ("index.html", "en.html"):
            fixture = FixtureServer(fallback=fallback)
            context, page, errors, unexpected = context_for(browser, fixture, 390)
            try:
                assert install(page, fixture)["state"] == "activated"
                fixture.requests.clear()
                page.goto(fixture.origin + "/" + name)
                css = page.locator(".hero").evaluate("e => getComputedStyle(e).backgroundImage")
                assert "banner.png" in css
                assert "/banner.png" in fixture.requests and "/banner.webp" not in fixture.requests, fixture.requests
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                cached = page.evaluate("async () => !!(await (await caches.open('mamourart-v7')).match(location.origin+'/banner.png'))")
                assert cached, "PNG fallback should be runtime-cached after its online use"
                context.set_offline(True)
                page.reload()
                image = page.evaluate("""async () => {const i=new Image(); i.src='/banner.png'; await i.decode(); return [i.naturalWidth,i.naturalHeight];}""")
                assert image == [2560, 1440], image
                report["fallback_simulations"].append({"page": name, "simulation": fallback, "online_and_offline_png": True, "dimensions": image, "png_bytes": (ROOT / "banner.png").stat().st_size})
                assert not errors and not unexpected, (errors, unexpected)
            finally:
                context.close()
                fixture.close()
    print("PASS eight FR/EN viewport banner cases: WebP only, 76,404 bytes; four explicit PNG fallback simulations with online runtime cache and offline decode", flush=True)


def clean_mobile_offline(browser, report):
    for width in (320, 390):
        for name in ("index.html", "en.html"):
            fixture = FixtureServer()
            context, page, errors, unexpected = context_for(browser, fixture, width)
            try:
                assert install(page, fixture)["state"] == "activated"
                page.goto(fixture.origin + "/" + name)
                assert "/banner.png" not in fixture.requests, fixture.requests
                context.set_offline(True)
                response = page.reload()
                assert response.status == 200
                css = page.locator(".hero").evaluate("e => getComputedStyle(e).backgroundImage")
                assert "image-set" in css and "banner.webp" in css
                image = page.evaluate("""async () => {const i=new Image(); i.src='/banner.webp'; await i.decode(); return [i.naturalWidth,i.naturalHeight];}""")
                assert image == [2560, 1440]
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                settle_hero(page)
                page.screenshot(path=str(OUTPUT / f"offline-{name.split('.')[0]}-{width}.png"))
                context.set_offline(False)
                assert page.reload().status == 200
                report["mobile_offline"].append({"page": name, "width": width, "offline_webp_dimensions": image, "reonline": True})
                assert not errors and not unexpected, (errors, unexpected)
            finally:
                context.close()
                fixture.close()
    print("PASS four clean mobile installs: precached WebP decoded after offline reload; reonline works; no PNG download during install/navigation", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--fixed-only", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {key: [] for key in ("baseline_precache", "baseline_banner", "rejected_installs", "updates", "responsive", "fallback_simulations", "mobile_offline")}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path="/usr/bin/chromium", headless=True,
            args=["--no-sandbox", "--disable-background-networking", "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"])
        try:
            if not args.fixed_only:
                baseline_reproductions(browser, report)
            if not args.baseline_only:
                rejected_installs(browser, report)
                update_and_offline(browser, report)
                responsive_and_fallback(browser, report)
                clean_mobile_offline(browser, report)
        finally:
            browser.close()
            suffix = "baseline" if args.baseline_only else "fixed" if args.fixed_only else "all"
            (OUTPUT / f"chromium42-{suffix}.json").write_text(json.dumps(report, indent=2))
    print("All fixture requests loopback-only; no PHP execution, form submission, production probe or mail.", flush=True)


if __name__ == "__main__":
    main()
