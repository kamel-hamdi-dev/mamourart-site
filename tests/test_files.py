from tests.checks import ROOT, parse_page, read_text

REQUIRED_FILES = (
    "index.html",
    "manifest.json",
    "robots.txt",
    "sitemap.xml",
    "service-worker.js",
    "logo.png",
    "banner.png",
    "dashboard.png",
    "icon-192.png",
    "icon-512.png",
)


def test_required_files_are_present_and_not_empty():
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    empty = [name for name in REQUIRED_FILES if (ROOT / name).is_file() and (ROOT / name).stat().st_size == 0]
    assert missing == [], f"missing files: {missing}"
    assert empty == [], f"empty files: {empty}"


def test_homepage_document():
    html = read_text("index.html")
    page = parse_page(html)

    assert html.lstrip().lower().startswith("<!doctype html>")
    assert page.language == "fr"
    assert "Mamourart" in page.title
    assert any(meta.get("charset", "").lower() == "utf-8" for meta in page.metas)
    assert page.meta_content.get("viewport")
    assert page.meta_content.get("description")
    assert html.lower().count("<h1") == 1
    assert len(page.ids) == len(set(page.ids))
