// Behavioral contract for the trusted inline script. No real network or browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {assertDecision} = require('./orchestrator_contract.cjs');
const [filename, language, scenario = 'webp', runId] = process.argv.slice(2);
assert.match(runId || '', /^[a-f0-9]{32}$/, 'Runtime requires a parent-issued run ID');
const code = fs.readFileSync(filename, 'utf8');
const calls = [], decodes = [], imageRequests = [], forbiddenCalls = [], handlers = new Map();
// Record BEFORE throwing: application code must not erase a forbidden attempt
// by catching the exception. This ledger belongs to the harness, not the VM.
const fail = name => function forbiddenOperationalAPI() {
  forbiddenCalls.push(name);
  throw Error('Forbidden operational API: ' + name);
};
function assertNoForbiddenCalls() {
  assert.deepEqual(forbiddenCalls, [], 'Forbidden operational API attempts: ' + forbiddenCalls.join(', '));
}
const result = {textContent:''};
const bitmap = {width:10, height:10, close() {}};
const ready = Promise.resolve({});
const worker = {state:'activated'};
const location = Object.freeze({href:'https://mamourart.test/ai-agent-orchestrator.html'});
const document = new Proxy({
  querySelectorAll(selector) {
    assert.equal(selector, '[data-decision]');
    return ['go', 'no-go', 'reset'].map(decision => ({
      dataset: Object.freeze({decision}),
      addEventListener(type, callback) {
        assert.equal(type, 'click');
        assert.ok(!handlers.has(decision));
        handlers.set(decision, callback);
      }
    }));
  },
  getElementById(id) { assert.equal(id, 'demo-result'); return result; }
}, {get(target, key) { assert.ok(key in target, 'Unexpected DOM API: ' + String(key)); return target[key]; }});
class Image {
  set src(value) {
    imageRequests.push(value);
    if (!/^\/(banner|logo)\.(webp|png)$/.test(value)) fail('Image.src')();
    this.source = value;
  }
  get src() { return this.source; }
  async decode() {
    assert.match(this.src, /^\/(banner|logo)\.(webp|png)$/);
    decodes.push(this.src);
    if (scenario === 'png' && this.src.endsWith('.webp')) throw Error('WebP decoder unavailable');
    if (scenario === 'broken-images') throw Error('No image decoder');
  }
}
const serviceWorker = {
  ready,
  async register(url) {
    calls.push(url);
    assert.equal(url, scenario === 'png' ? '/service-worker.js?banner=png&logo=png' : '/service-worker.js');
    return {active:worker};
  }
};
const window = {location};
const navigator = scenario === 'no-worker' ? {} : {serviceWorker};
navigator.sendBeacon = fail('sendBeacon');
const sandbox = {document, navigator, window, Image, URL, URLSearchParams,
  createImageBitmap: async image => {
    if (scenario === 'bitmap-png' && image.src.endsWith('.webp')) throw Error('WebP bitmap unavailable');
    return bitmap;
  },
  fetch:fail('fetch'), XMLHttpRequest:fail('XMLHttpRequest'), WebSocket:fail('WebSocket'),
  localStorage:new Proxy({}, {get:fail('localStorage')}),
  sessionStorage:new Proxy({}, {get:fail('sessionStorage')})};
// Browser aliases must be monitored too, including constructor calls.
Object.assign(window, {navigator, fetch:sandbox.fetch, XMLHttpRequest:sandbox.XMLHttpRequest,
  WebSocket:sandbox.WebSocket, Image});
// Exercise both possible WebP decoder failures, including the worker's decoder.
if (scenario === 'bitmap-png') serviceWorker.register = async url => {
  calls.push(url); assert.equal(url, '/service-worker.js?banner=png&logo=png'); return {active:worker};
};
let completed = false;
const incomplete = 'Runtime assertions did not complete';
// A pending Promise alone does not keep Node alive. Keep a bounded watchdog
// referenced until ALL assertions complete, with an exit guard as a backstop.
const watchdog = setTimeout(() => {
  console.error(incomplete);
  process.exitCode = 1;
}, 2000);
process.once('exit', () => {
  if (!completed && !process.exitCode) {
    console.error(incomplete);
    process.exitCode = 1;
  }
});
const settle = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  vm.runInNewContext(code, sandbox, {timeout:1000});
  assertNoForbiddenCalls();
  assert.deepEqual([...handlers.keys()], ['go','no-go','reset']);
  const readyResult = await window.mamourartOfflineReady;
  await settle();
  assertNoForbiddenCalls();
  assert.equal(readyResult, !['broken-images','no-worker'].includes(scenario), 'PWA installation readiness');
  let decisionsVerified = 0;
  for (const decision of ['go','no-go','reset','no-go','go']) {
    const before = JSON.stringify({calls,decodes,imageRequests});
    await handlers.get(decision)();
    await settle();
    assertNoForbiddenCalls();
    assertDecision(result.textContent, language, decision);
    assert.equal(JSON.stringify({calls,decodes,imageRequests}), before, 'Demo decisions must not initiate IO');
    decisionsVerified++;
  }
  assert.equal(calls.length, readyResult ? 1 : 0);
  if (scenario === 'webp') assert.deepEqual(decodes.sort(), ['/banner.webp','/logo.webp']);
  if (['png','bitmap-png'].includes(scenario)) assert.deepEqual(decodes.sort(), ['/banner.png','/banner.webp','/logo.png','/logo.webp']);
  await settle();
  assertNoForbiddenCalls();
  assert.equal(decisionsVerified, 5);
  console.log('PASS runtime', language, scenario, 'exact decisions, static image scope, no operational IO');
  console.log('ORCHESTRATOR_RUNTIME_COMPLETE ' + JSON.stringify({
    version:1, runId, language, scenario, decisionsVerified, assertionsComplete:true
  }));
  completed = true;
})().catch(error => {console.error(error);process.exitCode=1;})
  .finally(() => clearTimeout(watchdog));
