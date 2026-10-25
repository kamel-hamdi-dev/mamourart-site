// Local Chromium checks: no install, deployment or real operation.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');
const {EXPECTED, assertDecision, assertNetworkAnnotation} = require('./orchestrator_contract.cjs');
const ROOT = path.resolve(__dirname, '..');
const PAGES = ['ai-agent-orchestrator.html', 'ai-agent-orchestrator-en.html'];
const WIDTHS = [320,390,700,701,720,768,1000,1001,1024,1440];
const language = name => name.includes('-en') ? 'en' : 'fr';
let mode = 'normal';
const serverRequests = [], checks = [];
const server = http.createServer(async (request, response) => {
  const pathname = new URL(request.url, 'http://localhost').pathname;
  serverRequests.push({path:pathname, method:request.method});
  const file = path.resolve(ROOT, '.' + (pathname === '/' ? '/index.html' : pathname));
  if (!file.startsWith(ROOT + path.sep)) { response.writeHead(403).end(); return; }
  try {
    let body = await fs.readFile(file);
    // Faults exist in test responses only. Production source files are untouched.
    if (mode === 'wrong-go' && PAGES.includes(path.basename(file))) {
      const text = body.toString();
      const mutant = text.replace(/"go": "[^"]+"/, '"go": "NO-GO M-03"');
      assert.notEqual(mutant, text, 'The GO mutation must really be applied');
      body = Buffer.from(mutant);
    }
    if (mode === 'overflow' && PAGES.includes(path.basename(file))) {
      body = Buffer.from(body.toString().replace('</head>', '<style>.network .node small{white-space:nowrap;font-size:40px}</style></head>'));
    }
    if (mode === 'caught-fetch' && PAGES.includes(path.basename(file))) {
      const text = body.toString();
      const mutant = text.replace("button.addEventListener('click', () => {",
        "button.addEventListener('click', async () => { try { await fetch ('https://example.invalid/audit-caught-fetch'); } catch (_) {}");
      assert.notEqual(mutant, text, 'The caught-fetch mutation must really be applied');
      body = Buffer.from(mutant);
    }
    if (mode === 'stale-annotation' && ['index.html','en.html'].includes(path.basename(file))) {
      const text = body.toString();
      const mutant = text.replace(' data-i18n="orchestratorNetworkAnnotation"', '');
      assert.notEqual(mutant, text, 'The annotation mutation must really be applied');
      body = Buffer.from(mutant);
    }
    if (mode.startsWith('png') && pathname === '/service-worker.js') {
      body = Buffer.from("const nativeDecoder = createImageBitmap; self.createImageBitmap = blob => blob.type === 'image/webp' ? Promise.reject(new Error('Test: WebP unavailable')) : nativeDecoder(blob);\n" + body.toString());
    }
    const type = {'.html':'text/html; charset=utf-8', '.js':'application/javascript', '.json':'application/json', '.png':'image/png', '.webp':'image/webp', '.ico':'image/x-icon'}[path.extname(file)] || 'application/octet-stream';
    response.writeHead(200, {'Content-Type':type, 'Cache-Control':'no-cache'}).end(body);
  } catch (_) { response.writeHead(404).end(); }
});

async function assertInternalGeometry(page) {
  const overflows = await page.locator('.network .node, .network .node strong, .network .node small, .branch-node, .governance-steps li').evaluateAll(elements => elements.flatMap(element => {
    const parent = element.getBoundingClientRect();
    const overflow = element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1;
    const textChildren = [...element.children].filter(child => child instanceof HTMLElement);
    const outside = textChildren.some(child => {
      const box = child.getBoundingClientRect();
      return box.left < parent.left - 1 || box.right > parent.right + 1 || box.top < parent.top - 1 || box.bottom > parent.bottom + 1;
    });
    return overflow || outside ? [{text:element.innerText, width:element.clientWidth, scroll:element.scrollWidth, height:element.clientHeight, scrollHeight:element.scrollHeight}] : [];
  }));
  assert.deepEqual(overflows, [], 'Internal diagram overflow');
}

async function assertNetworkLanguage(page, lang) {
  assert.equal(await page.locator('html').getAttribute('lang'), lang);
  assert.equal(await page.locator('.network-annotation').count(), 1);
  assertNetworkAnnotation(await page.locator('.network-annotation').textContent(), lang);
}

(async () => {
  const publicNames = new Set(JSON.parse(await fs.readFile(path.join(ROOT,'deploy-manifest.json'),'utf8')).files.map(name => '/' + name));
  publicNames.add('/');
  await new Promise((resolve,reject) => { server.once('error',reject);server.listen(0,'127.0.0.1',resolve); });
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({headless:true, executablePath:process.env.MAAO_CHROMIUM || '/usr/bin/chromium'});
  async function monitoredContext(options = {}) {
    const context = await browser.newContext(options);
    const unexpected = [], errors = [];
    context.on('request', request => {
      const url = new URL(request.url());
      if (url.origin !== origin || request.method() !== 'GET' || !publicNames.has(url.pathname)) {
        unexpected.push(request.method() + ' ' + request.url());
      }
    });
    context.on('page', page => page.on('pageerror', error => errors.push(error.message)));
    await context.route('**/*', route => {
      const request = route.request(), url = new URL(request.url());
      return url.origin === origin && request.method() === 'GET' && publicNames.has(url.pathname) ? route.continue() : route.abort();
    });
    context.verify = () => {
      assert.deepEqual(unexpected, [], 'Unapproved request');
      assert.deepEqual(errors, [], 'No JavaScript errors');
    };
    return context;
  }
  try {
    const context = await monitoredContext({serviceWorkers:'block',reducedMotion:'reduce'});
    const page = await context.newPage();
    for (const name of PAGES) {
      console.log('Responsive FR/EN:',name);
      for (const width of WIDTHS) {
        await page.setViewportSize({width,height:900});
        await page.goto(origin+'/'+name);
        assert.equal(await page.locator('html').getAttribute('lang'),language(name));
        await assertNetworkLanguage(page,language(name));
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), name+' document overflow at '+width);
        await assertInternalGeometry(page);
        assert.equal(await page.locator('h1').count(),1);
        assert.equal(await page.locator('table tbody tr').count(),4);
        assert.equal(await page.locator('.metrics > *').count(),4);
        assert.ok(await page.locator('.table-wrap').evaluate(element => element.clientWidth >= element.closest('.dash-main').clientWidth-60));
        assert.equal(await page.locator('.modes .dark').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(7, 17, 31)');
        assert.equal(await page.evaluate(()=>document.getAnimations().length),0,'Reduced motion');
        for (const decision of ['go','no-go','reset']) {
          await page.locator(`[data-decision="${decision}"]`).click();
          assertDecision(await page.locator('#demo-result').textContent(),language(name),decision);
        }
        assert.match(await page.locator('tbody tr').nth(2).textContent(),/À valider|Pending approval/);
        assert.match(await page.locator('tbody tr').nth(3).textContent(),/NO-GO/);
        if ([390,1440].includes(width)) await page.screenshot({path:`/tmp/maao21-${name}-${width}.png`,fullPage:true});
        checks.push(name+' '+width+'px: internal geometry, exact decisions PASS');
      }
      await page.goto(origin+'/'+name);
      await page.keyboard.press('Tab');
      assert.equal(await page.locator(':focus').getAttribute('href'),'#main');
      await page.keyboard.press('Enter');
      await page.locator('[data-decision="go"]').focus();
      await page.keyboard.press('Enter');
      assertDecision(await page.locator('#demo-result').textContent(),language(name),'go');
      await page.locator('[data-decision="no-go"]').focus();
      await page.keyboard.press('Space');
      assertDecision(await page.locator('#demo-result').textContent(),language(name),'no-go');
      await page.locator('.lang a').click();
      assert.ok(page.url().endsWith('/'+PAGES.find(other=>other!==name)));
      await page.setViewportSize({width:390,height:900});
      await page.goto(origin+'/'+name);
      await page.locator('.mobile-nav summary').focus();
      await page.keyboard.press('Enter');
      assert.equal(await page.locator('.mobile-nav').getAttribute('open'),'');
      await page.locator('.mobile-nav-links a[href="#architecture"]').focus();
      await page.keyboard.press('Enter');
      assert.equal(new URL(page.url()).hash,'#architecture');
    }
    for (const [home,expected] of [['index.html',PAGES[0]],['en.html',PAGES[1]],['index.html?lang=en',PAGES[0]],['en.html?lang=fr',PAGES[1]]]) {
      await page.goto(origin+'/'+home);
      assert.ok((await page.locator('[data-orchestrator-link]').getAttribute('href')).endsWith(expected));
      const initialLanguage=language(expected);
      await assertNetworkLanguage(page,initialLanguage);
      // Exercise the real active-language setter, including a round trip. The
      // annotation must track it just like the existing node labels and links.
      for (const active of ['fr','en','fr','en',initialLanguage]) {
        await page.evaluate(lang=>setLanguage(lang),active);
        await assertNetworkLanguage(page,active);
        const target=active==='fr'?PAGES[0]:PAGES[1];
        assert.equal(await page.locator('[data-orchestrator-link]').getAttribute('href'),target);
      }
      for (const width of WIDTHS) {
        await page.setViewportSize({width,height:900});
        await assertInternalGeometry(page);
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Homepage overflow '+home+' '+width);
      }
      assert.equal(await page.locator('.orchestrator-card .orchestrator-art').count(),1);
      if (!home.includes('?')) await page.locator('.orchestrator-card').screenshot({path:`/tmp/maao21-card-${home}.png`});
      await page.locator('[data-orchestrator-link]').click();
      assert.ok(page.url().endsWith('/'+expected));
    }
    context.verify();await context.close();
    const nojs = await monitoredContext({javaScriptEnabled:false,viewport:{width:390,height:900}});
    for (const name of PAGES) {
      const p=await nojs.newPage();await p.goto(origin+'/'+name);
      assert.equal(await p.locator('table tbody tr').count(),4);
      await p.locator('.mobile-nav summary').click();
      await p.locator('.mobile-nav-links a[href="#architecture"]').click();
      assert.equal(new URL(p.url()).hash,'#architecture');
      // Test the language link from a fresh document, independently of an
      // in-progress native smooth scroll caused by the preceding anchor.
      await p.goto(origin+'/'+name);
      await p.locator('.lang a').click();
      assert.ok(p.url().endsWith('/'+PAGES.find(other=>other!==name)));
      await p.close();
    }
    nojs.verify();await nojs.close();
    // True direct visits: fresh contexts for each page and decoder condition.
    for (const scenario of ['webp','png-image','png-bitmap']) {
      mode=scenario==='webp'?'normal':scenario;
      for (const name of PAGES) {
        console.log('PWA direct:',scenario,name);
        const c=await monitoredContext();
        if (scenario==='png-image') await c.addInitScript(()=>{
          const native=HTMLImageElement.prototype.decode;
          HTMLImageElement.prototype.decode=function(){return this.src.endsWith('.webp')?Promise.reject(Error('Test: WebP image decoder unavailable')):native.call(this);};
        });
        if (scenario==='png-bitmap') await c.addInitScript(()=>{
          const native=createImageBitmap;
          window.createImageBitmap=source=>source instanceof HTMLImageElement&&source.src.endsWith('.webp')?Promise.reject(Error('Test: WebP bitmap decoder unavailable')):native(source);
        });
        const p=await c.newPage();await p.goto(origin+'/'+name);
        const installed=await p.evaluate(()=>Promise.race([window.mamourartOfflineReady,new Promise(resolve=>setTimeout(()=>resolve('timeout'),15000))]));
        assert.equal(installed,true,'PWA installation: '+scenario+' '+name);
        await p.waitForFunction(()=>!!navigator.serviceWorker.controller);
        const evidence=await p.evaluate(async()=>({script:(await navigator.serviceWorker.getRegistration()).active.scriptURL,
          caches:await Promise.all((await caches.keys()).map(async name=>({name,paths:(await (await caches.open(name)).keys()).map(request=>new URL(request.url).pathname)})))}));
        const cacheName='mamourart-v12'+(scenario==='webp'?'':'-png-logo-png');
        assert.equal(evidence.caches.length,1);
        assert.equal(evidence.caches[0].name,cacheName);
        const format=scenario==='webp'?'webp':'png';
        for(const stem of ['banner','logo'])assert.ok(evidence.caches[0].paths.includes('/'+stem+'.'+format));
        if(scenario!=='webp'){
          assert.ok(evidence.script.endsWith('?banner=png&logo=png'));
          assert.ok(!evidence.caches[0].paths.some(p=>p.endsWith('.webp')),'PNG cache must need no WebP decoder');
        } else assert.ok(evidence.script.endsWith('/service-worker.js'));
        await c.setOffline(true);
        for(const target of PAGES){
          await p.goto(origin+'/'+target);assert.equal(await p.locator('html').getAttribute('lang'),language(target));
          assert.equal(await p.locator('tbody tr').count(),4);
          await p.locator('[data-decision="go"]').click();assertDecision(await p.locator('#demo-result').textContent(),language(target),'go');
        }
        c.verify();await c.close();
        checks.push('PWA direct '+name+' '+scenario+': install, selected formats, offline FR/EN PASS');
      }
    }
    for (const name of PAGES) {
      mode='caught-fetch';
      const c=await monitoredContext({serviceWorkers:'block'}),p=await c.newPage();
      await p.goto(origin+'/'+name);
      await p.locator('[data-decision="go"]').click();
      await p.waitForFunction(text=>document.getElementById('demo-result').textContent===text,EXPECTED[language(name)].go);
      assertDecision(await p.locator('#demo-result').textContent(),language(name),'go');
      assert.throws(()=>c.verify(),/Unapproved request/,'A caught fetch must remain recorded');
      await c.close();
      checks.push('NEGATIVE '+name+': try/catch fetch correctly REJECTED despite a valid GO result');
    }
    for (const home of ['index.html','en.html']) {
      mode='stale-annotation';
      const c=await monitoredContext({serviceWorkers:'block',reducedMotion:'reduce'}),p=await c.newPage();
      await p.goto(origin+'/'+home);
      const initial=home==='index.html'?'fr':'en',opposite=initial==='fr'?'en':'fr';
      await assertNetworkLanguage(p,initial);
      await p.evaluate(lang=>setLanguage(lang),opposite);
      await assert.rejects(()=>assertNetworkLanguage(p,opposite),/Network annotation/);
      c.verify();await c.close();
      checks.push('NEGATIVE '+home+': original unsynchronized annotation correctly REJECTED after language switch');
    }
    mode='normal';
    // Negative checks exercise the SAME assertion functions as the positive suite.
    for(const name of PAGES){
      const c=await monitoredContext({serviceWorkers:'block',reducedMotion:'reduce'}),p=await c.newPage();
      mode='wrong-go';await p.goto(origin+'/'+name);await p.locator('[data-decision="go"]').click();
      assert.throws(()=>assertDecision('NO-GO M-03',language(name),'go'),/Exact go decision/);
      const actual=await p.locator('#demo-result').textContent();assert.equal(actual,'NO-GO M-03');
      assert.throws(()=>assertDecision(actual,language(name),'go'),/Exact go decision/);
      mode='overflow';await p.setViewportSize({width:701,height:900});await p.goto(origin+'/'+name);
      await assert.rejects(()=>assertInternalGeometry(p),/Internal diagram overflow/);
      c.verify();await c.close();
      checks.push('NEGATIVE '+name+': wrong GO and injected internal overflow correctly REJECTED');
    }
    mode='normal';
    const negative=await monitoredContext({serviceWorkers:'block'}),p=await negative.newPage();
    await p.goto(origin+'/'+PAGES[0]);
    await p.evaluate(()=>fetch('https://example.invalid/audit-probe').catch(()=>{}));
    assert.throws(()=>negative.verify(),/Unapproved request/);
    await negative.close();
    // Service-worker fetches can bypass page routing. Audit server-side methods
    // and paths too; no unapproved resource or operation may reach this server.
    assert.ok(serverRequests.every(r=>r.method==='GET'&&publicNames.has(r.path)),JSON.stringify(serverRequests.filter(r=>r.method!=='GET'||!publicNames.has(r.path))));
    checks.push('NEGATIVE external request correctly REJECTED (aborted before network)');
    console.log(checks.join('\n'));
    console.log('PASS local Chromium: layout, keyboard, languages, no JS, exact decisions, PNG fallback, negative proofs, no real operation');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>server.close());
