"""Public URL, deployment and executable offline regression checks."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from html.parser import HTMLParser

from tests.checks import ROOT, read_text


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ('src', 'srcset', 'href', 'action'):
            if key in attrs:
                self.urls.append(attrs[key])


def test_all_public_html_resources_and_language_urls_are_deployable():
    public = set(json.loads(read_text('deploy-manifest.json'))['files'])
    for name in ('index.html', 'en.html', 'legal.html', 'gps-ai-demo.html', 'fret-alerts-demo.html'):
        parser = Resources()
        parser.feed(read_text(name))
        for url in parser.urls:
            parsed = urlsplit(url)
            if parsed.scheme or not parsed.path:
                continue
            path = parsed.path.lstrip('/') or 'index.html'
            assert path in public, (name, path)
            assert (ROOT / path).is_file(), (name, path)
    for name, lang, canonical in [('index.html', 'fr', '/'), ('en.html', 'en', '/en.html')]:
        html = read_text(name)
        assert f'<html lang="{lang}">' in html
        assert f'rel="canonical" href="https://mamourart.com{canonical}"' in html
        assert 'hreflang="fr" href="https://mamourart.com/"' in html
        assert 'hreflang="en" href="https://mamourart.com/en.html"' in html
        assert 'navigator.language' not in html
    assert 'Custom software for your business operations.' in read_text('en.html').split('<script>')[0]
    # Identical executable logic in the two static pages.
    assert read_text('index.html').split('<script>')[1] == read_text('en.html').split('<script>')[1]
    form = re.search(r'<form .*?</form>', read_text('index.html'), re.S)[0]
    assert hashlib.sha256(form.encode()).hexdigest() == 'd86d468b7ef46e1995906638ca28bda0087de2ffbbb6972a483b463c53810004'



def test_worker_offline_runtime(tmp_path):
    harness = tmp_path / 'worker.cjs'
    harness.write_text(r'''
const assert = require('node:assert/strict');
const vm = require('node:vm'), fs = require('node:fs');
const events = {}, data = new Map(), removed = [];
const cache = {addAll: async paths => {for(const path of paths) data.set('https://mamourart.com'+path, new Response(path));},
  put: async (key, response) => data.set(key, response), match: async key => data.get(key)?.clone()};
let online = false, status = 200, privateResponse = false;
const context = {URL, Response, Set, self: {location: {origin: 'https://mamourart.com'},
 addEventListener: (name, cb) => events[name] = cb, skipWaiting: async()=>{}, clients:{claim:async()=>{}}},
 caches:{open:async()=>cache, keys:async()=>['mamourart-v4','mamourart-v5','other-app'],delete:async name=>removed.push(name)},
 fetch: async()=>{if(!online) throw Error('offline'); const response = new Response('network', {status, headers: privateResponse?{'Cache-Control':'private'}:{}});
 Object.defineProperty(response,'type',{value:'basic'}); return response;}};
vm.createContext(context); vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
async function lifecycle(name){let done;events[name]({waitUntil:p=>done=p});await done;}
async function request(path, method='GET', mode='navigate'){
 let done; events.fetch({request:{url:'https://mamourart.com'+path,method,mode},respondWith:p=>done=p});
 return done ? await done : null;
}
(async()=>{
 await lifecycle('install'); await lifecycle('activate');
 assert.deepEqual(removed,['mamourart-v4']);
 for(const path of ['/','/index.html','/en.html','/legal.html','/gps-ai-demo.html','/fret-alerts-demo.html']) {
   assert.equal(await (await request(path)).text(), path);
   data.delete('https://mamourart.com'+path);
   const missing=await request(path); assert.equal(missing.status,503);
   assert.match(await missing.text(), /offline|hors ligne/);
 }
 assert.equal((await request('/missing.html')).status,503);
 for(const path of ['/contact-submit.php','/contact-rate-limit.php','/?contact_status=sent','/index.html?token=secret'])
   assert.equal(await request(path),null);
 assert.equal(await request('/index.html','POST'),null);
 online=true; status=404; assert.equal((await request('/legal.html')).status,404);
 status=200; privateResponse=true; await request('/legal.html');
 assert.equal(data.has('https://mamourart.com/legal.html'),false);
 privateResponse=false; await request('/legal.html?lang=en'); online=false;
 assert.equal(await (await request('/legal.html?lang=fr')).text(),'network');
 assert.equal((await request('/unknown.png','GET','cors')).type,undefined); // bypass
})().catch(e=>{console.error(e);process.exit(1)});
'''.replace("assert.equal((await request('/unknown.png','GET','cors')).type,undefined);", "assert.equal(await request('/unknown.png','GET','cors'),null);"))
    result = subprocess.run(['node', str(harness), str(ROOT / 'service-worker.js')], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
