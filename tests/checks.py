"""Shared readers for the static site checks."""

import re
import struct
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"


def read_text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        raise AssertionError(f"{path.name} is not a PNG")
    width, height = struct.unpack(">II", data[16:24])
    if width < 1 or height < 1:
        raise AssertionError(f"{path.name} has invalid dimensions {width}x{height}")
    if not data.endswith(PNG_IEND):
        raise AssertionError(f"{path.name} is missing the PNG end marker")
    return width, height


def site_file(url_path: str) -> Path:
    """Map a site-root path to a file in the repository."""
    if url_path in ("", "/"):
        return ROOT / "index.html"
    relative = url_path.lstrip("/")
    candidate = (ROOT / relative).resolve()
    if not candidate.is_relative_to(ROOT.resolve()):
        raise AssertionError(f"{url_path} escapes the site directory")
    return candidate


def style_urls(html: str) -> list[str]:
    blocks = re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.I | re.S)
    pattern = re.compile(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", re.I)
    return [match.group(1).strip() for block in blocks for match in pattern.finditer(block)]


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.language = ""
        self.title = ""
        self.ids: list[str] = []
        self.anchors: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.metas: list[dict[str, str]] = []
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._stack.append(tag)
        attr = {key.lower(): value or "" for key, value in attrs}
        if tag == "html":
            self.language = attr.get("lang", "")
        if attr.get("id"):
            self.ids.append(attr["id"])
        if tag == "a" and "href" in attr:
            self.anchors.append(attr)
        elif tag == "img":
            self.images.append(attr)
        elif tag == "meta":
            self.metas.append(attr)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._stack and self._stack[-1] == "title":
            self.title += data

    @property
    def meta_content(self) -> dict[str, str]:
        return {meta["name"]: meta.get("content", "") for meta in self.metas if meta.get("name")}


def parse_page(html: str) -> Page:
    page = Page()
    page.feed(html)
    page.close()
    return page
