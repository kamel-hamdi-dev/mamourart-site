// Behavioral service-worker model. No network request is made by this harness.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const ORIGIN = 'https://mamourart.test';
const PRECACHE = ['/', '/index.html', '/en.html', '/legal.html', '/gps-ai-demo.html',
  '/fret-alerts-demo.html', '/logo.webp', '/banner.webp', '/manifest.json',
  '/icon-192.png', '/icon-512.png', '/favicon.ico'];
const [workerPath, scenario = 'runtime'] = process.argv.slice(2);
let source = fs.readFileSync(workerPath, 'utf8');
const current = source.match(/CACHE_NAME\s*=\s*['"]([^'"]+)/)[1];
const version = Number(current.match(/\d+$/)[0]);
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
let skipWaiting = 0, claimed = 0, putAttempts = 0;

function makeResponse(url, options = {}) {
  // A network response URL never contains a request's client-side fragment.
  const networkURL = new URL(url); networkURL.hash = '';
  const metadata = {url: options.url ?? networkURL.href, type: options.type ?? 'basic',
    redirected: options.redirected ?? false, status: options.status ?? 200};
  const response = new Response(Object.hasOwn(options, 'body') ? options.body : new URL(url).pathname,
    {status: metadata.status >= 200 ? metadata.status : 200, headers: options.headers ?? {}});
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
  assert.equal(options.cache ?? request.cache, 'no-cache', 'public responses must be revalidated');
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
      'empty-url': {url: ''}, 'null-body': {body: null}
    };
    if (rejected[scenario]) config = {...config, ...rejected[scenario]};
    if (/^http-/.test(scenario)) config = {...config, status: Number(scenario.slice(5)), headers: {Location: '/index.html'}};
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
        return [requestURL(request), response];
      }));
      for (const [url, response] of candidates) { entries.set(url, response.clone()); writes.push({url, response}); }
    },
    async put(request, response) {
      if (failPut || (failPutAt && ++putAttempts === failPutAt)) throw Error('cache write failed');
      const url = requestURL(request);
      entries.set(url, response.clone()); writes.push({url, response});
    },
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
  URL, Response, Request, Set, Promise,
  self: {location: {origin: ORIGIN}, addEventListener: (name, callback) => events[name] = callback,
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
  let completion;
  events[name]({waitUntil: promise => completion = promise});
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
  assert.ok(stores.get(previous).has(ORIGIN + '/index.html'));
  for (const name of ['other-app', 'mamourart-vx', 'mamourart-v5-extra']) assert.ok(stores.has(name), name);
}

async function installScenario() {
  if (scenario === 'cache-open') failOpen = true;
  if (scenario === 'cache-write') failPutAt = 2;
  if (scenario === 'cleanup-failure') { failPutAt = 2; failDelete = true; }
  if (scenario === 'safe' || scenario === 'transition') {
    await lifecycle('install');
    assert.equal(skipWaiting, 1); assert.equal(claimed, 0);
    previousPreserved();
    assert.deepEqual([...stores.get(current).keys()].sort(), PRECACHE.map(path => ORIGIN + path).sort());
    for (const path of PRECACHE) {
      const response = stores.get(current).get(ORIGIN + path).clone();
      assert.equal(response.url, ORIGIN + path); assert.equal(response.type, 'basic');
      assert.equal(response.status, 200); assert.equal(await response.text(), path);
    }
    await lifecycle('activate');
    assert.equal(claimed, 1); assert.ok(!stores.has(previous));
    assert.ok(stores.has(current));
    for (const name of ['other-app', 'mamourart-vx', 'mamourart-v5-extra']) assert.ok(stores.has(name), name);
    online = false;
    assert.equal(await (await request('/index.html')).text(), '/index.html');
    assert.equal(await (await request('/en.html')).text(), '/en.html');
    assert.equal((await request('/missing.html')).status, 503);
    online = true;
    assert.equal((await request('/index.html')).status, 200);
    return;
  }
  await assert.rejects(lifecycle('install'), undefined, scenario + ' must abort installation');
  assert.equal(skipWaiting, 0, 'failed install must never request activation');
  assert.equal(claimed, 0); previousPreserved();
  if (scenario === 'cleanup-failure') {
    assert.equal(stores.get(current)?.size, 1, 'failed cleanup may leave only an unactivated safe partial cache');
  } else {
    assert.ok(!stores.has(current) || stores.get(current).size === 0,
      'failed installation must not leave a partial current-version cache');
  }
  if (!['cache-write', 'cleanup-failure'].includes(scenario))
    assert.equal(writes.length, 0, 'validate all candidate responses before any cache insertion');
  for (const {url, response} of writes) {
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
  for (const path of ['/', '/index.html', '/en.html', '/legal.html', '/gps-ai-demo.html', '/fret-alerts-demo.html']) {
    assert.equal(await (await request(path)).text(), path);
    data.delete(ORIGIN + path);
    const missing = await request(path); assert.equal(missing.status, 503);
    assert.equal(missing.headers.get('Cache-Control'), 'no-store');
    assert.match(await missing.text(), /offline|hors ligne/);
  }
  assert.equal((await request('/missing.html')).status, 503);
  assert.match(await (await request('/en.html')).text(), /lang="en"/);
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
    assert.equal(await (await request('/legal.html')).text(), '/legal.html');
    assert.equal(data.has(ORIGIN + '/legal.html'), false);
  }
  headers = {}; redirected = false; responseType = 'basic'; runtimeURLOverride = null;
  assert.equal(await (await request('/legal.html?lang=en#privacy-en')).text(), '/legal.html');
  assert.equal(data.has(ORIGIN + '/legal.html'), true,
    'a public request fragment must not prevent caching its safe network response');
  assert.equal(data.get(ORIGIN + '/legal.html').url, ORIGIN + '/legal.html?lang=en');
  data.delete(ORIGIN + '/legal.html');
  failPut = true; assert.equal(await (await request('/legal.html')).text(), '/legal.html');
  assert.equal(data.has(ORIGIN + '/legal.html'), false); failPut = false;
  failOpen = true; assert.equal(await (await request('/legal.html')).text(), '/legal.html');
  online = false; assert.equal((await request('/legal.html')).status, 503); failOpen = false;
  failMatch = true; assert.equal((await request('/legal.html')).status, 503); failMatch = false;
  online = true; await request('/legal.html?lang=en'); online = false;
  assert.equal(await (await request('/legal.html?lang=fr')).text(), '/legal.html');
  assert.equal(await request('/unknown.png', 'GET', 'cors'), null);
  data.delete(ORIGIN + '/dashboard.webp');
  assert.equal((await request('/dashboard.webp', 'GET', 'cors')).type, 'error');
  online = true; assert.equal(await (await request('/dashboard.webp', 'GET', 'cors')).text(), '/dashboard.webp');
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
