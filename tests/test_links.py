from urllib.parse import urlparse

from tests.checks import ROOT, parse_page, read_text, site_file

SECTIONS = ("top", "services", "projects", "approach", "contact")
CONTACT = "mailto:contact@mamourart.com"
PUBLISHED_LINKS = {
    "https://github.com/kamel-hamdi-dev/mamourart-transport-automation",
    "https://www.mamourart.com/",
    "https://www.linkedin.com/in/kamel-hamdi-dev/",
    "https://github.com/kamel-hamdi-dev",
}


def page():
    return parse_page(read_text("index.html"))


def test_section_links_point_at_existing_ids():
    document = page()
    hrefs = {anchor["href"] for anchor in document.anchors}

    assert set(document.ids) >= set(SECTIONS)
    for section in SECTIONS:
        assert f"#{section}" in hrefs


def test_every_href_is_a_known_kind():
    for anchor in page().anchors:
        href = anchor["href"].strip()
        assert href, "anchor is missing an href"
        assert not href.startswith("//"), href
        assert not href.lower().startswith(("javascript:", "data:")), href
        if href.startswith("#"):
            assert len(href) > 1, href
        elif href.startswith("mailto:"):
            continue
        elif href.startswith("https://"):
            assert urlparse(href).hostname, href
        elif href.startswith("/") or ":" not in href:
            continue
        else:
            raise AssertionError(f"unsupported link: {href}")


def test_fragment_and_relative_links_resolve():
    document = page()
    for anchor in document.anchors:
        href = anchor["href"]
        if href.startswith("#"):
            assert href[1:] in document.ids, href
            continue
        if href.startswith(("mailto:", "https:", "http:")):
            continue
        target = site_file(urlparse(href).path or "/")
        assert target.is_file(), href


def test_mailto_and_published_links():
    hrefs = {anchor["href"] for anchor in page().anchors}
    assert CONTACT in hrefs
    assert PUBLISHED_LINKS <= hrefs
    for href in hrefs:
        if not href.startswith("mailto:"):
            continue
        address = href.removeprefix("mailto:").split("?", 1)[0]
        local, separator, domain = address.partition("@")
        assert separator and local and "." in domain, href


def test_new_tab_links_keep_noopener():
    for anchor in page().anchors:
        if anchor.get("target") != "_blank":
            continue
        rel = set(anchor.get("rel", "").split())
        assert "noopener" in rel, anchor["href"]
        assert anchor["href"].startswith("https://")


def test_internal_asset_paths_stay_inside_the_repository():
    for anchor in page().anchors:
        href = anchor["href"]
        if href.startswith(("#", "mailto:", "https:", "http:")):
            continue
        target = site_file(urlparse(href).path or "/")
        assert target.is_relative_to(ROOT.resolve())
