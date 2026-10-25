// Behavioral service-worker model. No network request is made by this harness.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const ROOT = path.resolve(__dirname, '..');
function resource(url) { return fs.readFileSync(path.join(ROOT, new URL(url, ORIGIN).pathname.slice(1) || 'index.html')); }
function expectedText(url) { return resource(url).toString(); }
function mimeFor(url) {
 const ext = path.extname(new URL(url).pathname);
 return ({'.png':'image/png','.webp':'image/webp','.ico':'image/x-icon','.json':'application/json'})[ext] || 'text/html; charset=utf-8';
}

const ORIGIN = 'https://mamourart.test';
const PRECACHE = ['/', '/index.html', '/en.html', '/legal.html', '/gps-ai-demo.html',
  '/fret-alerts-demo.html', '/ai-agent-orchestrator.html', '/ai-agent-orchestrator-en.html', '/logo.webp', '/banner.webp', '/manifest.json',
  '/icon-192.png', '/icon-512.png', '/favicon.ico'];
const [workerPath, scenario = 'runtime'] = process.argv.slice(2);
let source = fs.readFileSync(workerPath, 'utf8');
const pngVariant = scenario === 'png-variant';
if (pngVariant) for (const stem of ['logo', 'banner']) PRECACHE[PRECACHE.indexOf('/' + stem + '.webp')] = '/' + stem + '.png';
const current = source.match(/CACHE_NAME\s*=\s*['"]([^'"]+)/)[1] + (pngVariant ? '-png-logo-png' : '');
const version = Number(current.match(/\d+/)[0]);
const previous = `mamourart-v${version - 1}`;
const events = {}, removed = [], writes = [], fetched = [];
const stores = new Map([
  [previous, new Map([[ORIGIN + '/index.html', makeResponse(ORIGIN + '/index.html', {body: 'previous valid page'})]])],
  ['mamourart-v4', new Map()], ['other-app', new Map()], ['mamourart-vx', new Map()],
  ['mamourart-v5-extra', new Map()]
]);
let online = true, status = 200, headers = {}, redirected = false, responseType = 'basic';
let failOpen = false, failPut = false, failMatch = false, failPutAt = 0, failDelete = false;
let runtimeURLOverride = null;
let failEntryDelete = false;
let skipWaiting = 0, claimed = 0, putAttempts = 0;

function makeResponse(url, options = {}) {
  // A network response URL never contains a request's client-side fragment.
  const networkURL = new URL(url); networkURL.hash = '';
  const metadata = {url: options.url ?? networkURL.href, type: options.type ?? 'basic',
    redirected: options.redirected ?? false, status: options.status ?? 200};
  const responseHeaders = new Headers({'Content-Type': mimeFor(url)});
  for (const [key, value] of Object.entries(options.headers ?? {})) responseHeaders.set(key, value);
  const response = new Response(Object.hasOwn(options, 'body') ? options.body : resource(url),
    {status: metadata.status >= 200 ? metadata.status : 200, headers: responseHeaders});
  function decorate(value) {
    Object.defineProperties(value, {
      url: {value: metadata.url}, type: {value: metadata.type}, redirected: {value: metadata.redirected},
      status: {value: metadata.status}, ok: {value: metadata.status >= 200 && metadata.status < 300},
      clone: {value() { return decorate(Response.prototype.clone.call(this)); }}
    });
    return value;
  }
  return decorate(response);
}

function requestURL(request) {
  return new URL(typeof request === 'string' || request instanceof URL ? request : request.url, ORIGIN).href;
}

async function fetchResponse(request, options = {}) {
  const url = requestURL(request);
  const method = options.method ?? request.method ?? 'GET';
  fetched.push({url, method, options});
  assert.equal(method, 'GET', 'precache and runtime network requests must remain GET');
  assert.equal(options.cache ?? request.cache, /^\/(banner|logo)\./.test(new URL(url).pathname) ? 'force-cache' : 'no-cache', 'only selected banner/logo may reuse HTTP cache');
  if (!online || (scenario === 'network' && new URL(url).pathname === '/legal.html')) throw Error('network unavailable');
  const candidate = new URL(url).pathname === '/legal.html';
  let config = {status, headers, redirected, type: responseType};
  if (runtimeURLOverride !== null) config.url = runtimeURLOverride;
  if (candidate) {
    const rejected = {
      'no-store': {headers: {'Cache-Control': 'public, no-store'}},
      private: {headers: {'Cache-Control': 'private, max-age=60'}},
      'vary-star': {headers: {'Vary': 'Accept-Language, *'}},
      redirected: {redirected: true, url: ORIGIN + '/index.html'},
      opaque: {status: 0, type: 'opaque', url: ''},
      cors: {type: 'cors'}, default: {type: 'default'}, error: {status: 0, type: 'error', url: ''},
      'foreign-origin': {url: 'https://unexpected.invalid/legal.html'},
      'wrong-path': {url: ORIGIN + '/contact-submit.php'},
      'private-result-url': {url: ORIGIN + '/?contact_status=sent'},
      'empty-url': {url: ''}, 'null-body': {body: null},
      'empty-body': {body: ''}, 'wrong-mime': {headers: {'Content-Type': 'image/png'}},
      'missing-mime': {headers: {'Content-Type': ''}}, 'invalid-html': {body: 'not an HTML page'},
      'invalid-utf8': {body: new Uint8Array([0xff, 0xfe])},
      'oversized-body': {body: 'x'.repeat(512 * 1024 + 1)},
      'read-error': {body: new ReadableStream({start(c) {c.error(Error('interrupted stream'));}})},
      'truncated-stream': {body: new ReadableStream({start(c) {c.enqueue(new TextEncoder().encode('<!doctype html>')); c.error(Error('truncated stream'));}})}
    };
    if (rejected[scenario]) config = {...config, ...rejected[scenario]};
    if (/^http-/.test(scenario)) config = {...config, status: Number(scenario.slice(5)), headers: {Location: '/index.html'}};
  }
  if (new URL(url).pathname === '/manifest.json') {
    if (scenario === 'invalid-json') config.body = '{bad json';
    if (scenario === 'invalid-manifest') config.body = '{"name":"Mamourart","icons":[]}';
  }
  if (new URL(url).pathname === '/icon-192.png') {
    if (scenario === 'invalid-image') config.body = 'not a PNG';
    if (scenario === 'truncated-image') config.body = resource(url).subarray(0, 24);
    if (scenario === 'image-wrong-encoding') config.body = fs.readFileSync(path.join(ROOT, 'banner.webp'));
    if (scenario === 'image-wrong-mime') config.headers = {'Content-Type': 'text/html'};
  }
  const response = makeResponse(url, config);
  if (candidate && scenario === 'body-used') await response.text();
  return response;
}

function cacheFor(name) {
  if (!stores.has(name)) stores.set(name, new Map());
  const entries = stores.get(name);
  return {
    // Cache.addAll itself does not reject private/no-store/followed redirects.
    // Model that API faithfully so the old worker demonstrably fails the new tests.
    async addAll(requests) {
      const candidates = await Promise.all(requests.map(async request => {
        const response = await fetchResponse(request, {cache: 'no-cache'});
        if (!response.ok || response.headers.get('Vary')?.includes('*')) throw Error('addAll rejected response');
        const body = await response.arrayBuffer();
        return [requestURL(request), makeResponse(requestURL(request), {body, url:response.url,
          type:response.type, redirected:response.redirected, status:response.status,
          headers:Object.fromEntries(response.headers)})];
      }));
      for (const [url, response] of candidates) { entries.set(url, response.clone()); writes.push({url, response, body: Buffer.from(body)}); }
    },
    async put(request, response) {
      if (failPut || (failPutAt && ++putAttempts === failPutAt)) throw Error('cache write failed');
      const url = requestURL(request);
      // Like real Cache.put, consume the supplied body to completion. A read
      // error must reject the operation before the entry is visible.
      const body = await response.arrayBuffer();
      entries.set(url, makeResponse(url, {body, url: response.url, type: response.type,
        redirected: response.redirected, status: response.status, headers: Object.fromEntries(response.headers)}));
      writes.push({url, response, body: Buffer.from(body)});
      if (scenario === 'stored-corruption' && new URL(url).pathname === '/legal.html') {
        entries.set(url, makeResponse(url, {body: 'corrupt stored bytes'}));
      }
    },
    async keys() { return [...entries.keys()]; },
    async delete(request) { return failEntryDelete ? Promise.reject(Error('entry cleanup failed')) : entries.delete(requestURL(request)); },
    async match(request) {
      if (failMatch) throw Error('cache read failed');
      return entries.get(requestURL(request))?.clone();
    }
  };
}

const injection = {
  'request-foreign': 'https://unexpected.invalid/legal.html',
  'request-protocol-relative': '//unexpected.invalid/legal.html',
  'request-php': '/contact-submit.php',
  'request-result': '/?contact_status=sent',
  'request-query': '/legal.html?token=secret',
  'request-fragment': '/legal.html#private'
};
if (injection[scenario]) source = source.replace(/const FILES_TO_CACHE\s*=\s*\[/,
  match => match + JSON.stringify(injection[scenario]) + ',');

const context = {
  URL, Response, Request, Set, Promise, Blob, TextDecoder, Uint8Array, DataView,
  // Node has no browser image decoder. Accept only the exact official image
  // fixtures here; Chromium tests exercise createImageBitmap on real payloads.
  createImageBitmap: async blob => {
    if (pngVariant) assert.notEqual(blob.type, 'image/webp', 'a browser without WebP must never need to decode a precache WebP');
    const bytes = Buffer.from(await blob.arrayBuffer());
    assert.ok(['logo.png','logo.webp','banner.webp','banner.png','icon-192.png','icon-512.png','favicon.ico','dashboard.webp']
      .some(name => bytes.equals(fs.readFileSync(path.join(ROOT, name)))), 'invalid image fixture');
    return {width:1,height:1,close(){}};
  },
  self: {location: {origin: ORIGIN, href: ORIGIN + '/service-worker.js' + (pngVariant ? '?banner=png&logo=png' : '')}, addEventListener: (name, callback) => events[name] = callback,
    skipWaiting: async () => { skipWaiting++; }, clients: {claim: async () => { claimed++; }}},
  caches: {
    open: async name => { if (failOpen) throw Error('cache unavailable'); return cacheFor(name); },
    keys: async () => [...stores.keys()],
    delete: async name => { if (failDelete) throw Error('cache cleanup failed'); removed.push(name); return stores.delete(name); }
  },
  fetch: fetchResponse
};
vm.createContext(context);
vm.runInContext(source, context);

async function lifecycle(name) {
  let completion, calls = 0;
  assert.equal(typeof events[name], 'function');
  events[name]({waitUntil: promise => { calls++; completion = promise; }});
  assert.equal(calls, 1, name + ' must register exactly one lifetime promise');
  assert.ok(completion, name + ' must extend its lifetime');
  return completion;
}

async function request(path, method = 'GET', mode = 'navigate') {
  let completion;
  events.fetch({request: {url: new URL(path, ORIGIN).href, method, mode}, respondWith: promise => completion = promise});
  return completion ? await completion : null;
}

function previousPreserved() {
  assert.ok(stores.has(previous), 'failed installation must preserve the previously valid cache');
  assert.equal(stores.get(previous).size, 1);
  assert.ok(stores.get(previous).has(ORIGIN + '/index.html'));
  assert.equal(stores.get(previous).get(ORIGIN + '/index.html').bodyUsed, false);
  for (const name of ['other-app', 'mamourart-vx', 'mamourart-v5-extra']) assert.ok(stores.has(name), name);
}

async function installScenario() {
  if (scenario === 'cache-open') failOpen = true;
  if (scenario === 'cache-write') failPutAt = 2;
  if (['cleanup-failure', 'cleanup-total-failure'].includes(scenario)) { failPutAt = 2; failDelete = true; }
  if (scenario === 'cleanup-total-failure') failEntryDelete = true;
  if (scenario === 'safe' || scenario === 'transition' || scenario === 'activation-corruption' || pngVariant) {
    await lifecycle('install');
    assert.equal(skipWaiting, 1); assert.equal(claimed, 0);
    previousPreserved();
    assert.deepEqual([...stores.get(current).keys()].sort(), PRECACHE.map(path => ORIGIN + path).sort());
    for (const path of PRECACHE) {
      const response = stores.get(current).get(ORIGIN + path).clone();
      assert.equal(response.url, ORIGIN + path); assert.equal(response.type, 'basic');
      assert.equal(response.status, 200); assert.equal(await response.text(), expectedText(path));
    }
    if (scenario === 'activation-corruption') {
      stores.get(current).set(ORIGIN + '/legal.html', makeResponse(ORIGIN + '/legal.html', {body: 'corrupt storage'}));
      await assert.rejects(lifecycle('activate'), /Invalid stored precache response/);
      assert.equal(claimed, 0); previousPreserved();
      assert.ok(!removed.includes(previous));
      return;
    }
    await lifecycle('activate');
    assert.equal(claimed, 1); assert.ok(!stores.has(previous));
    assert.ok(stores.has(current));
    for (const name of ['other-app', 'mamourart-vx', 'mamourart-v5-extra']) assert.ok(stores.has(name), name);
    online = false;
    assert.equal(await (await request('/index.html')).text(), expectedText('/index.html'));
    assert.equal(await (await request('/en.html')).text(), expectedText('/en.html'));
    assert.equal((await request('/missing.html')).status, 503);
    online = true;
    assert.equal((await request('/index.html')).status, 200);
    return;
  }
  const expectedError = injection[scenario] ? /^Invalid public precache URL$/ :
    scenario === 'network' ? /^network unavailable$/ :
    scenario === 'stored-corruption' ? /^Invalid stored precache response$/ :
    scenario === 'cache-open' ? /^cache unavailable$/ :
    ['cache-write', 'cleanup-failure', 'cleanup-total-failure'].includes(scenario) ? /^cache write failed$/ : /^Unsafe precache response$/;
  await assert.rejects(lifecycle('install'), error => {
    assert.match(error.message, expectedError, scenario + ' must fail for its intended cause');
    return true;
  });
  assert.equal(skipWaiting, 0, 'failed install must never request activation');
  assert.equal(claimed, 0); previousPreserved();
  if (scenario === 'cleanup-total-failure') {
    assert.equal(stores.get(current)?.size, 1, 'failed cleanup may leave only an unactivated safe partial cache');
    const residue = stores.get(current);
    await assert.rejects(lifecycle('activate'), /Incomplete precache candidate/);
    assert.equal(claimed, 0); previousPreserved();
    failPutAt = 0;
    await assert.rejects(lifecycle('install'), /entry cleanup failed/);
    assert.equal(stores.get(current), residue); assert.equal(skipWaiting, 0); previousPreserved();
    failDelete = false; failEntryDelete = false;
    await lifecycle('install');
    assert.equal(skipWaiting, 1);
    assert.deepEqual([...stores.get(current).keys()].sort(), PRECACHE.map(path => ORIGIN + path).sort());
    for (const path of PRECACHE) assert.deepEqual(Buffer.from(await stores.get(current).get(ORIGIN + path).clone().arrayBuffer()), resource(path));
    previousPreserved();
    await lifecycle('activate'); assert.equal(claimed, 1);

  } else {
    assert.ok(!stores.has(current) || stores.get(current).size === 0,
      'failed installation must not leave a partial current-version cache');
  }
  if (!['cache-write', 'cleanup-failure', 'cleanup-total-failure', 'stored-corruption'].includes(scenario))
    assert.equal(writes.length, 0, 'validate all candidate responses before any cache insertion');
  for (const {url, response, body} of writes) {
    assert.deepEqual(body, resource(url), "only complete official fixture bodies may be stored");
    assert.equal(response.status, 200); assert.equal(response.type, 'basic'); assert.equal(response.redirected, false);
    assert.equal(response.url, url); assert.doesNotMatch(response.headers.get('Cache-Control') ?? '', /private|no-store/i);
  }
  if (injection[scenario]) assert.ok(!fetched.some(({url}) => url === requestURL(injection[scenario])),
    'invalid candidate must be rejected before a network request');
}

async function runtimeScenario() {
  // Retains and extends every behavioral assertion from Mission 40's inline model.
  online = false;
  await assert.rejects(lifecycle('install'), /network unavailable/);
  assert.equal(skipWaiting, 0); assert.ok(!stores.has(current) || stores.get(current).size === 0);
  online = true;
  await lifecycle('install'); await lifecycle('activate');
  assert.equal(skipWaiting, 1); assert.equal(claimed, 1);
  assert.ok(removed.includes(previous)); assert.ok(removed.includes('mamourart-v4'));
  for (const name of ['other-app', 'mamourart-vx', 'mamourart-v5-extra']) assert.ok(stores.has(name));
  const data = stores.get(current);
  assert.deepEqual([...data.keys()].sort(), PRECACHE.map(path => ORIGIN + path).sort());
  online = false;
  for (const path of ['/', '/index.html', '/en.html', '/legal.html', '/gps-ai-demo.html', '/fret-alerts-demo.html', '/ai-agent-orchestrator.html', '/ai-agent-orchestrator-en.html']) {
    assert.equal(await (await request(path)).text(), expectedText(path));
    data.delete(ORIGIN + path);
    const missing = await request(path); assert.equal(missing.status, 503);
    assert.equal(missing.headers.get('Cache-Control'), 'no-store');
    assert.match(await missing.text(), /offline|hors ligne/);
  }
  assert.equal((await request('/missing.html')).status, 503);
  assert.match(await (await request('/en.html')).text(), /lang="en"/);
  assert.match(await (await request('/ai-agent-orchestrator-en.html')).text(), /lang="en"/);
  assert.match(await (await request('/ai-agent-orchestrator.html')).text(), /lang="fr"/);
  assert.match(await (await request('/legal.html?lang=en')).text(), /lang="en"/);
  assert.match(await (await request('/legal.html?lang=fr')).text(), /lang="fr"/);
  const beforeBypass = fetched.length;
  for (const path of ['/contact-submit.php', '/contact-submit.php?lang=en', '/contact-rate-limit.php',
    '/index.html?token=secret', '/index.html?lang=unknown', 'https://other-app.invalid/index.html'])
    assert.equal(await request(path), null);
  for (const path of ['/', '/index.html', '/en.html']) for (const result of ['sent', 'error'])
    assert.equal(await request(path + '?contact_status=' + result), null);
  for (const method of ['POST', 'HEAD', 'OPTIONS']) assert.equal(await request('/index.html', method), null);
  assert.equal(fetched.length, beforeBypass);
  // Invalid runtime bodies must never replace a previously valid offline page.
  online = true; await request('/legal.html');
  const saved = data.get(ORIGIN + '/legal.html');
  assert.ok(saved);
  for (const [body, contentType] of [['', 'text/html'], ['garbage', 'text/html'], ['PNG', 'image/png']]) {
    const originalFetch = context.fetch;
    context.fetch = async req => makeResponse(requestURL(req), {body, headers: {'Content-Type': contentType}});
    const response = await request('/legal.html');
    assert.equal(await response.text(), body, 'online response remains visible');
    assert.equal(data.get(ORIGIN + '/legal.html'), saved, 'invalid runtime body must preserve the stored entry');
    context.fetch = originalFetch;
  }
  data.delete(ORIGIN + '/legal.html');
  online = true; status = 404; assert.equal((await request('/legal.html')).status, 404);
  assert.equal(data.has(ORIGIN + '/legal.html'), false); status = 200;
  for (const excluded of [
    {headers: {'Cache-Control': 'private'}}, {headers: {'Cache-Control': 'public, no-store'}},
    {headers: {'Vary': 'Accept-Language, *'}}, {redirected: true}, {type: 'opaque'},
    {url: 'https://unexpected.invalid/legal.html'}, {url: ORIGIN + '/wrong.html'},
    {url: ORIGIN + '/legal.html?contact_status=sent'}
  ]) {
    headers = excluded.headers ?? {}; redirected = excluded.redirected ?? false; responseType = excluded.type ?? 'basic';
    runtimeURLOverride = excluded.url ?? null;
    assert.equal(await (await request('/legal.html')).text(), expectedText('/legal.html'));
    assert.equal(data.has(ORIGIN + '/legal.html'), false);
  }
  headers = {}; redirected = false; responseType = 'basic'; runtimeURLOverride = null;
  assert.equal(await (await request('/legal.html?lang=en#privacy-en')).text(), expectedText('/legal.html'));
  assert.equal(data.has(ORIGIN + '/legal.html'), true,
    'a public request fragment must not prevent caching its safe network response');
  assert.equal(data.get(ORIGIN + '/legal.html').url, ORIGIN + '/legal.html?lang=en');
  data.delete(ORIGIN + '/legal.html');
  failPut = true; assert.equal(await (await request('/legal.html')).text(), expectedText('/legal.html'));
  assert.equal(data.has(ORIGIN + '/legal.html'), false); failPut = false;
  failOpen = true; assert.equal(await (await request('/legal.html')).text(), expectedText('/legal.html'));
  online = false; assert.equal((await request('/legal.html')).status, 503); failOpen = false;
  failMatch = true; assert.equal((await request('/legal.html')).status, 503); failMatch = false;
  online = true; await request('/legal.html?lang=en'); online = false;
  assert.equal(await (await request('/legal.html?lang=fr')).text(), expectedText('/legal.html'));
  assert.equal(await request('/unknown.png', 'GET', 'cors'), null);
  data.delete(ORIGIN + '/dashboard.webp');
  assert.equal((await request('/dashboard.webp', 'GET', 'cors')).type, 'error');
  online = true; assert.equal(await (await request('/dashboard.webp', 'GET', 'cors')).text(), expectedText('/dashboard.webp'));
}

(scenario === 'runtime' ? runtimeScenario() : installScenario())
  .then(() => console.log('PASS service worker ' + scenario))
  .catch(error => {
    const legal = stores.get(current)?.get(ORIGIN + '/legal.html');
    console.error(error);
    console.error('Cache evidence: ' + JSON.stringify({scenario, writes: writes.length, skipWaiting, claimed,
      legal: legal && {status: legal.status, type: legal.type, redirected: legal.redirected, url: legal.url,
        cacheControl: legal.headers.get('Cache-Control')}}));
    process.exitCode = 1;
  });
