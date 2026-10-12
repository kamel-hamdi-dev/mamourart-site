import json

from tests.checks import ROOT, parse_page, png_size, read_text

DISPLAY_MODES = {"standalone", "fullscreen", "minimal-ui", "browser"}


def manifest() -> dict:
    return json.loads(read_text("manifest.json"))


def test_manifest_is_json_with_required_fields():
    data = manifest()
    for field in ("name", "short_name", "description", "start_url", "scope", "display", "icons"):
        assert data.get(field), field
    assert data["name"] == "Mamourart"
    assert data["short_name"] == "Mamourart"
    assert data["start_url"] == "/"
    assert data["scope"] == "/"
    assert data["display"] in DISPLAY_MODES
    assert data["display"] == "standalone"


def test_manifest_colors_match_the_page_theme():
    data = manifest()
    theme = parse_page(read_text("index.html")).meta_content["theme-color"]
    assert data["theme_color"] == theme
    assert data["background_color"] == theme
    assert theme.startswith("#") and len(theme) == 7


def test_manifest_icons_match_png_files():
    icons = manifest()["icons"]
    assert len(icons) >= 2
    seen = set()
    for icon in icons:
        src = icon["src"]
        assert src.startswith("/")
        path = ROOT / src.lstrip("/")
        assert path.is_file(), src
        width, height = png_size(path)
        assert icon["sizes"] == f"{width}x{height}"
        assert icon["type"] == "image/png"
        seen.add(path.name)
    assert seen >= {"icon-192.png", "icon-512.png"}
