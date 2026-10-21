"""Static banner contract; actual resource selection is checked by Chromium."""
import re
from html.parser import HTMLParser

import pytest

from tests.checks import read_text


class Preloads(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.images = []
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == 'link' and attributes.get('rel') == 'preload' and attributes.get('as') == 'image':
            self.images.append(attributes)


def compact(value):
    return re.sub(r'\s+', '', value)


def assert_banner_contract(html):
    css = re.search(r'<style>(.*?)</style>', html, re.S).group(1)
    assert 'image-set(' not in css, 'picture must be the only banner selector'
    assert 'url("banner.' not in css, 'CSS must not compete with the selected image'
    overlays = re.findall(r'\.hero::before\s*\{([^{}]*)\}', css)
    assert len(overlays) == 2
    assert 'linear-gradient(90deg,rgba(7,17,31,.95)0%,rgba(7,17,31,.9)72%,rgba(7,17,31,.38)86%,rgba(7,17,31,.1)100%)' in compact(overlays[0])
    assert 'linear-gradient(180deg,rgba(7,17,31,.9)0%,rgba(7,17,31,.78)48%,rgba(7,17,31,.7)100%)' in compact(overlays[1])
    framing = re.findall(r'\.hero-banner img\s*\{([^{}]*)\}', css)
    assert len(framing) == 2
    assert 'object-fit:cover' in compact(framing[0])
    assert 'object-position:rightcenter' in compact(framing[0])
    assert 'object-position:72%center' in compact(framing[1])
    assert 'isolation:isolate' in compact(css)
    assert '<picture class="hero-banner" aria-hidden="true">' in html
    assert '<source srcset="banner.webp" type="image/webp">' in html
    assert '<img id="heroBanner" src="banner.png" alt="" width="2560" height="1440" fetchpriority="high" decoding="async">' in html
    assert not Preloads(html).images, 'Native picture selection must have no competing preload'
    assert 'banner.decode()' in html
    assert 'source.remove()' in html
    assert 'banner.src = "banner.png"' in html
    assert 'banner.png?' not in html and 'banner.webp?' not in html


@pytest.mark.parametrize('name', ['index.html', 'en.html'])
def test_banner_source_fallback_and_framing_match_across_responsive_rules(name):
    assert_banner_contract(read_text(name))


def test_homepages_share_the_same_banner_styles():
    rules = [re.findall(r'(?<![\w-])\.hero\s*\{([^{}]*)\}', read_text(name)) for name in ('index.html', 'en.html')]
    assert [compact(rule) for rule in rules[0]] == [compact(rule) for rule in rules[1]]
