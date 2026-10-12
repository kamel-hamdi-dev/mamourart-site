from urllib.parse import urlparse

from tests.checks import ROOT, parse_page, png_size, read_text, site_file, style_urls


def test_html_images_exist_and_have_alt_text():
    images = parse_page(read_text("index.html")).images
    assert images, "the page has no images"
    for image in images:
        src = image.get("src", "")
        alt = image.get("alt", "").strip()
        assert src, "image is missing a src"
        assert alt, f"{src} is missing alt text"
        assert not src.lower().startswith(("javascript:", "data:"))
        if src.startswith("https://"):
            assert urlparse(src).hostname
            continue
        path = site_file(urlparse(src).path)
        assert path.is_file(), src
        png_size(path)


def test_css_images_exist():
    urls = style_urls(read_text("index.html"))
    assert "banner.png" in {urlparse(url).path.lstrip("/") for url in urls}
    for url in urls:
        if url.startswith(("data:", "https:", "http:")):
            continue
        path = site_file(urlparse(url).path)
        assert path.is_file(), url
        png_size(path)


def test_icon_files_have_declared_pixel_sizes():
    assert png_size(ROOT / "icon-192.png") == (192, 192)
    assert png_size(ROOT / "icon-512.png") == (512, 512)


def test_every_png_in_the_site_root_is_readable():
    pngs = sorted(ROOT.glob("*.png"))
    assert {path.name for path in pngs} >= {
        "logo.png",
        "banner.png",
        "dashboard.png",
        "icon-192.png",
        "icon-512.png",
    }
    for path in pngs:
        width, height = png_size(path)
        assert width > 0 and height > 0
