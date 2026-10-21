"""Applied integration: semantic FR/EN form contract for the combined PRs."""
from html.parser import HTMLParser
import pytest
from tests.checks import read_text

class Form(HTMLParser):
    def __init__(self, html):
        super().__init__(); self.form = None; self.controls = {}; self.options = []
        self.trap = None; self.result = None; self.submit = None; self.privacy = None
        self.inside = False; self.feed(html)
    def handle_starttag(self, tag, pairs):
        a = dict(pairs)
        if tag == 'form':
            assert self.form is None
            self.form = a; self.inside = True
        if not self.inside: return
        if 'name' in a:
            assert a['name'] not in self.controls
            self.controls[a['name']] = (tag, a)
        if tag == 'option': self.options.append(a.get('value'))
        if a.get('class') == 'quote-trap': self.trap = a
        if a.get('id') == 'quoteResult': self.result = a
        if tag == 'button': self.submit = a
        if a.get('data-legal-link') == 'privacy': self.privacy = a
    def handle_endtag(self, tag):
        if tag == 'form': self.inside = False

def assert_secure_form(html, lang):
    form = Form(html)
    assert form.form == {'class':'quote-form', 'method':'post',
        'action':'contact-submit.php' + ('?lang=en' if lang == 'en' else ''), 'accept-charset':'UTF-8'}
    assert form.controls == {
        'name': ('input', {'name':'name','autocomplete':'name','minlength':'2','maxlength':'120','required':None}),
        'company': ('input', {'name':'company','autocomplete':'organization','maxlength':'120'}),
        'email': ('input', {'name':'email','type':'email','autocomplete':'email','maxlength':'254','required':None}),
        'service': ('select', {'name':'service','required':None}),
        'details': ('textarea', {'name':'details','rows':'5','minlength':'20','maxlength':'3500','required':None}),
        'privacy_ack': ('input', {'name':'privacy_ack','type':'checkbox','value':'yes','required':None}),
        'website': ('input', {'type':'text','name':'website','tabindex':'-1','autocomplete':'off'}),
    }
    assert form.options == ['', 'software', 'web', 'automation', 'transport', 'other']
    assert form.trap == {'class':'quote-trap','aria-hidden':'true'}
    assert form.result == {'class':'quote-result','id':'quoteResult','role':'status','aria-live':'polite','tabindex':'-1'}
    assert form.submit == {'class':'button primary','type':'submit','data-i18n':'quoteSend'}
    assert form.privacy['href'] == f'legal.html?lang={lang}#privacy-{lang}'
    assert 'data-i18n="quotePrivacyInfo"' in html
    assert 'data-i18n="quoteFallback"' in html

def test_both_forms_keep_security_semantics():
    for name, lang in [('index.html','fr'), ('en.html','en')]: assert_secure_form(read_text(name), lang)

@pytest.mark.parametrize('old,new', [
    ('minlength="2"','minlength="1"'), ('maxlength="120"','maxlength="121"'),
    ('type="checkbox" value="yes" required','type="checkbox" value="yes"'),
    ('aria-hidden="true"','aria-hidden="false"'), ('name="website"','name="unknown"'),
    ('value="transport"','value="untrusted"'), ('method="post"','method="get"'),
])
def test_semantic_contract_detects_security_regression(old, new):
    with pytest.raises(AssertionError): assert_secure_form(read_text('index.html').replace(old,new), 'fr')
