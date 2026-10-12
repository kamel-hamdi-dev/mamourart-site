"""Network checks for the https links published on the page.

Marked ``external`` so a public-network or LinkedIn failure stays out of the
required Python site checks.
"""

import urllib.error
import urllib.request
from urllib.parse import urlparse

import pytest

from tests.checks import parse_page, read_text

USER_AGENT = "Mozilla/5.0 (compatible; MamourartSiteCheck/1.0; +https://mamourart.com/)"

pytestmark = pytest.mark.external


def test_external_links_respond():
    hrefs = sorted(
        {
            anchor["href"]
            for anchor in parse_page(read_text("index.html")).anchors
            if anchor["href"].startswith("https://")
        }
    )
    assert hrefs, "the page has no external links"
    failures = []
    for href in hrefs:
        status = _status(href)
        print(f"{href} -> {status}")
        if not _acceptable(href, status):
            failures.append(f"{href} -> {status}")
    assert failures == [], "external links failed: " + ", ".join(failures)


def _status(url: str) -> int | str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        reason = getattr(error, "reason", error)
        return f"unreachable ({reason})"


def _acceptable(url: str, status: int | str) -> bool:
    if not isinstance(status, int):
        return False
    if 200 <= status < 400:
        return True
    host = urlparse(url).hostname or ""
    # LinkedIn answers 999 to automated clients instead of a normal page status.
    return host.endswith("linkedin.com") and status == 999
