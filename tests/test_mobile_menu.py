"""Execute the real homepage script against a small DOM event harness in Node."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tests.checks import read_text


HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const lang = process.argv[3];
const document = {activeElement: null, documentElement: {lang}, listeners: {},
  addEventListener(type, callback) { this.listeners[type] = callback; },
  querySelectorAll() { return []; }, querySelector() { return null; }};
function element(attributes = {}) {
  const classes = new Set();
  return {attributes, listeners: {}, focusCalls: 0,
    classList: {
      toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); },
      contains(name) { return classes.has(name); }},
    getAttribute(name) { return this.attributes[name] ?? null; },
    setAttribute(name, value) { this.attributes[name] = value; },
    addEventListener(type, callback) { this.listeners[type] = callback; },
    contains(target) { return target === this; },
    focus() { document.activeElement = this; this.focusCalls++; }};
}
const menu = element({'aria-expanded': 'false'});
const links = [element(), element()];
const nav = element();
nav.querySelectorAll = () => links;
nav.contains = target => target === nav || links.includes(target);
const fr = element(), en = element(), outside = element();
const elements = {menuToggle: menu, navLinks: nav, frButton: fr, enButton: en};
document.getElementById = id => elements[id] ?? null;
const window = {innerWidth: 390, location: {search: '', hash: ''}, listeners: {},
  addEventListener(type, callback) { this.listeners[type] = callback; }};
const storage = new Map([['mamourart-language-v2', lang]]);
const context = {document, window, navigator: {language: lang}, URLSearchParams,
  localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context);
function openMenu() { menu.focus(); menu.listeners.click(); }
function assertClosed() {
  assert.equal(menu.getAttribute('aria-expanded'), 'false');
  assert.equal(nav.classList.contains('is-open'), false);
}
// Escape from a menu link must close and restore focus exactly once.
openMenu();
assert.equal(menu.getAttribute('aria-expanded'), 'true');
links[0].focus();
document.listeners.keydown({key: 'Tab'});
assert.equal(document.activeElement, links[0]);
const before = menu.focusCalls;
document.listeners.keydown({key: 'Escape'});
assertClosed();
assert.equal(document.activeElement, menu);
assert.equal(menu.focusCalls, before + 1);
assert.equal(menu.getAttribute('aria-label'), lang === 'fr' ? 'Ouvrir le menu' : 'Open menu');
// A closed menu must not steal focus, including from either language button.
for (const control of [outside, fr, en]) {
  control.focus();
  document.listeners.keydown({key: 'Escape'});
  assert.equal(document.activeElement, control);
  assert.equal(menu.focusCalls, before + 1);
}
// Other ways of closing must not request focus on the menu trigger.
openMenu(); outside.focus();
let count = menu.focusCalls;
document.listeners.click({target: outside});
assertClosed(); assert.equal(document.activeElement, outside);
assert.equal(menu.focusCalls, count);
openMenu(); links[0].focus(); count = menu.focusCalls;
links[0].listeners.click();
assertClosed(); assert.equal(menu.focusCalls, count);
openMenu(); outside.focus(); count = menu.focusCalls;
window.innerWidth = 1440; window.listeners.resize();
assertClosed(); assert.equal(document.activeElement, outside);
assert.equal(menu.focusCalls, count);
// Language selection still updates the selected state without moving focus.
for (const [language, control, other] of [['en', en, fr], ['fr', fr, en]]) {
  control.focus(); context.setLanguage(language);
  assert.equal(document.activeElement, control);
  assert.equal(document.documentElement.lang, language);
  assert.equal(control.getAttribute('aria-pressed'), 'true');
  assert.equal(other.getAttribute('aria-pressed'), 'false');
}
console.log('PASS mobile menu focus: ' + lang);
"""


@pytest.mark.parametrize("language", ["fr", "en"])
def test_mobile_menu_focus_behavior(language):
    node = shutil.which("node")
    assert node, "node is required to execute the homepage menu regression test"
    scripts = re.findall(r"<script>(.*?)</script>", read_text("index.html"), re.S)
    assert len(scripts) == 1
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "homepage.js"
        harness = Path(directory) / "menu-harness.js"
        script.write_text(scripts[0], encoding="utf-8")
        harness.write_text(HARNESS, encoding="utf-8")
        result = subprocess.run(
            [node, str(harness), str(script), language],
            capture_output=True, text=True, check=False, timeout=15,
        )
    assert result.returncode == 0, result.stdout + result.stderr
