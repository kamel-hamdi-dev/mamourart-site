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
    hero_rules = re.findall(r'(?<![\w-])\.hero\s*\{([^{}]*)\}', css)
    assert len(hero_rules) == 2, 'Expected desktop and mobile hero rules'
    expected_gradients = [
        'linear-gradient(90deg,rgba(7,17,31,.95)0%,rgba(7,17,31,.9)72%,rgba(7,17,31,.38)86%,rgba(7,17,31,.1)100%)',
        'linear-gradient(180deg,rgba(7,17,31,.9)0%,rgba(7,17,31,.78)48%,rgba(7,17,31,.7)100%)',
    ]
    for rule, gradient, position in zip(hero_rules, expected_gradients, ['center,rightcenter', 'center,72%center']):
        declarations = re.findall(r'([\w-]+)\s*:\s*([^;]+)(?:;|$)', rule)
        images = [compact(value) for property_name, value in declarations if property_name == 'background-image']
        assert len(images) == 2, 'Each responsive rule needs PNG fallback followed by typed image-set'
        assert images[0] == gradient + ',url("banner.png")', 'PNG fallback must preserve framing and use the unversioned public path'
        assert images[1] == gradient + ',image-set(url("banner.webp")type("image/webp"),url("banner.png")type("image/png"))', 'Selected responsive image must prefer WebP without losing the PNG alternative'
        assert not any(property_name == 'background' for property_name, _ in declarations), 'Shorthand must not reset the selected image'
        assert compact(dict(declarations)['background-position']) == position
    assert compact(dict(re.findall(r'([\w-]+)\s*:\s*([^;]+)(?:;|$)', hero_rules[0]))['background-size']) == 'cover,cover'
    assert 'banner.png?' not in css and 'banner.webp?' not in css
    preloads = Preloads(html).images
    assert len(preloads) == 1, 'Avoid contradictory image preloads'
    assert preloads[0]['href'] == 'banner.webp'
    assert preloads[0]['type'] == 'image/webp'
    assert preloads[0]['fetchpriority'] == 'high'


@pytest.mark.parametrize('name', ['index.html', 'en.html'])
def test_banner_source_fallback_and_framing_match_across_responsive_rules(name):
    assert_banner_contract(read_text(name))


def test_homepages_share_the_same_banner_styles():
    rules = [re.findall(r'(?<![\w-])\.hero\s*\{([^{}]*)\}', read_text(name)) for name in ('index.html', 'en.html')]
    assert [compact(rule) for rule in rules[0]] == [compact(rule) for rule in rules[1]]
