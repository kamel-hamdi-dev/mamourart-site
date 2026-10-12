import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from tests.checks import ROOT, read_text

SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
HOSTS = {"mamourart.com", "www.mamourart.com"}


def test_sitemap_lists_the_homepage():
    root = ET.fromstring(read_text("sitemap.xml"))
    assert root.tag == f"{{{SITEMAP_NS['sm']}}}urlset"
    locs = [node.text.strip() for node in root.findall("sm:url/sm:loc", SITEMAP_NS)]
    assert "https://mamourart.com/" in locs
    for loc in locs:
        parsed = urlparse(loc)
        assert parsed.scheme == "https", loc
        assert parsed.hostname in HOSTS, loc
        assert not parsed.query and not parsed.fragment
    priorities = [node.text.strip() for node in root.findall("sm:url/sm:priority", SITEMAP_NS)]
    for priority in priorities:
        value = float(priority)
        assert 0.0 <= value <= 1.0


def test_robots_sitemap_points_at_a_local_file():
    text = read_text("robots.txt")
    assert re.search(r"^User-agent:\s*\*\s*$", text, re.M)
    assert re.search(r"^Allow:\s*/\s*$", text, re.M)
    match = re.search(r"^Sitemap:\s*(\S+)\s*$", text, re.M)
    assert match, "robots.txt has no Sitemap line"
    parsed = urlparse(match.group(1))
    assert parsed.scheme == "https"
    assert parsed.hostname in HOSTS
    local = ROOT / parsed.path.lstrip("/")
    assert local.is_file()
    ET.fromstring(local.read_text(encoding="utf-8"))
