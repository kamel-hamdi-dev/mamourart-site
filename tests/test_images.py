from urllib.parse import urlparse
from PIL import Image


def image_size(path):
    if path.suffix.lower() == ".png":
        return png_size(path)

    if path.suffix.lower() == ".webp":
        with Image.open(path) as img:
            assert img.format == "WEBP", f"{path.name} is not a valid WebP"
            img.verify()

        with Image.open(path) as img:
            width, height = img.size
            assert width > 0 and height > 0
            img.load()
            return width, height

    raise AssertionError(f"Unsupported image format: {path.name}")
from tests.checks import ROOT, parse_page, png_size, read_text, site_file, style_urls


def test_html_images_exist_and_have_alt_text():
    images = parse_page(read_text("index.html")).images
    assert images, "the page has no images"
    for image in images:
        src = image.get("src", "")
        alt = image.get("alt", "").strip()
        assert src, "image is missing a src"
        if image.get("id") == "heroBanner":
            assert image.get("alt") == "" and src == "banner.png"
            assert '<picture class="hero-banner" aria-hidden="true">' in read_text("index.html")
        else:
            assert alt, f"{src} is missing alt text"
        assert not src.lower().startswith(("javascript:", "data:"))
        if src.startswith("https://"):
            assert urlparse(src).hostname
            continue
        path = site_file(urlparse(src).path)
        assert path.is_file(), src
        image_size(path)


def test_css_images_exist():
    urls = style_urls(read_text("index.html"))
    # The decorative banner moved from CSS to picture; verify its resource too.
    banner = next(image for image in parse_page(read_text("index.html")).images if image.get("id") == "heroBanner")
    assert banner["src"] == "banner.png"
    assert image_size(ROOT / banner["src"]) == (2560, 1440)
    for url in urls:
        if url.startswith(("data:", "https:", "http:")):
            continue
        path = site_file(urlparse(url).path)
        assert path.is_file(), url
        image_size(path)

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
