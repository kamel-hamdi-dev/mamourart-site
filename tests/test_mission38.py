"""Public URL, deployment and executable offline regression checks."""
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from html.parser import HTMLParser

from tests.checks import ROOT, read_text


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ('src', 'srcset', 'href', 'action'):
            if key in attrs:
                self.urls.append(attrs[key])


def test_all_public_html_resources_and_language_urls_are_deployable():
    public = set(json.loads(read_text('deploy-manifest.json'))['files'])
    for name in ('index.html', 'en.html', 'legal.html', 'gps-ai-demo.html', 'fret-alerts-demo.html'):
        parser = Resources()
        parser.feed(read_text(name))
        for url in parser.urls:
            parsed = urlsplit(url)
            if parsed.scheme or not parsed.path:
                continue
            path = parsed.path.lstrip('/') or 'index.html'
            assert path in public, (name, path)
            assert (ROOT / path).is_file(), (name, path)
    for name, lang, canonical in [('index.html', 'fr', '/'), ('en.html', 'en', '/en.html')]:
        html = read_text(name)
        assert f'<html lang="{lang}">' in html
        assert f'rel="canonical" href="https://mamourart.com{canonical}"' in html
        assert 'hreflang="fr" href="https://mamourart.com/"' in html
        assert 'hreflang="en" href="https://mamourart.com/en.html"' in html
        assert 'navigator.language' not in html
    assert 'Custom software for your business operations.' in read_text('en.html').split('<script>')[0]
    # Identical executable logic in the two static pages.
    assert read_text('index.html').split('<script>')[1] == read_text('en.html').split('<script>')[1]
    from tests.test_integration39d import assert_secure_form
    assert_secure_form(read_text('index.html'), 'fr')
    assert_secure_form(read_text('en.html'), 'en')



def test_worker_offline_runtime():
    result = subprocess.run(
        ['node', str(ROOT / 'tests/worker_mission42.cjs'), str(ROOT / 'service-worker.js'), 'runtime'],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS service worker runtime" in result.stdout
