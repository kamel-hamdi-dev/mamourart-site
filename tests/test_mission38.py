"""Public URL, deployment and executable offline regression checks."""
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
    from tests.test_integration39d import assert_secure_form
    assert_secure_form(read_text('index.html'), 'fr')
    assert_secure_form(read_text('en.html'), 'en')



def test_worker_offline_runtime(tmp_path):
    harness = tmp_path / 'worker.cjs'
    harness.write_text(r'''
const assert = require('node:assert/strict');
const vm = require('node:vm'), fs = require('node:fs');
const events = {}, data = new Map(), removed = [];
let online = false, status = 200, headers = {}, redirected = false, responseType = 'basic';
let failInstall = false, failOpen = false, failPut = false, failMatch = false;
let activated = 0, claimed = 0, fetches = 0;
const cache = {
 addAll: async paths => {
   if(failInstall) throw Error('precache failed');
   for(const path of paths) data.set('https://mamourart.com'+path, new Response(path));
 },
 put: async (key, response) => {if(failPut) throw Error('cache write failed'); data.set(key, response);},
 match: async key => {if(failMatch) throw Error('cache read failed'); return data.get(key)?.clone();}
};
const context = {URL, Response, Set, self: {location: {origin: 'https://mamourart.com'},
 addEventListener: (name, cb) => events[name] = cb, skipWaiting: async()=>{activated++;}, clients:{claim:async()=>{claimed++;}}},
 caches:{open:async name=>{assert.equal(name,'mamourart-v6'); if(failOpen) throw Error('cache unavailable'); return cache;},
 keys:async()=>['mamourart-v4','mamourart-v5','mamourart-v6','other-app','mamourart-vx','mamourart-v5-extra'],
 delete:async name=>removed.push(name)},
 fetch: async(request, options)=>{
   fetches++; assert.equal(options.cache,'no-cache');
   if(!online) throw Error('offline');
   const response = new Response('network', {status, headers});
   Object.defineProperty(response,'type',{value:responseType});
   Object.defineProperty(response,'redirected',{value:redirected}); return response;
 }};
vm.createContext(context); vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
async function lifecycle(name){let done;events[name]({waitUntil:p=>done=p});await done;}
async function request(path, method='GET', mode='navigate'){
 let done; events.fetch({request:{url:path.startsWith('https:')?path:'https://mamourart.com'+path,method,mode},respondWith:p=>done=p});
 return done ? await done : null;
}
(async()=>{
 failInstall=true; await assert.rejects(lifecycle('install'),/precache failed/);
 assert.equal(activated,0); assert.equal(data.size,0); failInstall=false;
 await lifecycle('install'); await lifecycle('activate');
 assert.equal(activated,1); assert.equal(claimed,1);
 assert.deepEqual(removed,['mamourart-v4','mamourart-v5']);
 assert.deepEqual([...data.keys()].sort(),['/','/index.html','/en.html','/legal.html','/gps-ai-demo.html',
   '/fret-alerts-demo.html','/logo.webp','/banner.webp','/manifest.json','/icon-192.png','/icon-512.png','/favicon.ico']
   .map(path=>'https://mamourart.com'+path).sort());
 for(const path of ['/','/index.html','/en.html','/legal.html','/gps-ai-demo.html','/fret-alerts-demo.html']) {
   assert.equal(await (await request(path)).text(), path);
   data.delete('https://mamourart.com'+path);
   const missing=await request(path); assert.equal(missing.status,503);
   assert.equal(missing.headers.get('Cache-Control'),'no-store');
   assert.match(await missing.text(), /offline|hors ligne/);
 }
 assert.equal((await request('/missing.html')).status,503);
 assert.match(await (await request('/en.html')).text(),/lang="en"/);
 assert.match(await (await request('/legal.html?lang=en')).text(),/lang="en"/);
 assert.match(await (await request('/legal.html?lang=fr')).text(),/lang="fr"/);
 const beforeBypass=fetches;
 for(const path of ['/contact-submit.php','/contact-submit.php?lang=en','/contact-rate-limit.php',
   '/index.html?token=secret','/index.html?lang=unknown','https://other-app.invalid/index.html'])
   assert.equal(await request(path),null);
 for(const path of ['/','/index.html','/en.html']) for(const result of ['sent','error'])
   assert.equal(await request(path+'?contact_status='+result),null);
 for(const method of ['POST','HEAD','OPTIONS']) assert.equal(await request('/index.html',method),null);
 assert.equal(fetches,beforeBypass);
 online=true; status=404; assert.equal((await request('/legal.html')).status,404);
 assert.equal(data.has('https://mamourart.com/legal.html'),false); status=200;
 for(const excluded of [
   {headers:{'Cache-Control':'private'}}, {headers:{'Cache-Control':'public, no-store'}},
   {headers:{'Vary':'Accept-Language, *'}}, {headers:{},redirected:true}, {headers:{},responseType:'opaque'}
 ]) {
   headers=excluded.headers; redirected=excluded.redirected||false; responseType=excluded.responseType||'basic';
   assert.equal(await (await request('/legal.html')).text(),'network');
   assert.equal(data.has('https://mamourart.com/legal.html'),false);
 }
 headers={}; redirected=false; responseType='basic';
 failPut=true; assert.equal(await (await request('/legal.html')).text(),'network');
 assert.equal(data.has('https://mamourart.com/legal.html'),false); failPut=false;
 failOpen=true; assert.equal(await (await request('/legal.html')).text(),'network');
 online=false; assert.equal((await request('/legal.html')).status,503); failOpen=false;
 failMatch=true; assert.equal((await request('/legal.html')).status,503); failMatch=false;
 online=true; await request('/legal.html?lang=en'); online=false;
 assert.equal(await (await request('/legal.html?lang=fr')).text(),'network');
 assert.equal(await request('/unknown.png','GET','cors'),null);
 data.delete('https://mamourart.com/dashboard.webp');
 assert.equal((await request('/dashboard.webp','GET','cors')).type,'error');
 online=true; assert.equal(await (await request('/dashboard.webp','GET','cors')).text(),'network');
})().catch(e=>{console.error(e);process.exit(1)});
''')
    result = subprocess.run(['node', str(harness), str(ROOT / 'service-worker.js')], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
