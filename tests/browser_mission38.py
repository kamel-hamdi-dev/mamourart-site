"""Optional local Chromium check: python tests/browser_mission38.py (Playwright required)."""
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
from threading import Thread
from playwright.sync_api import sync_playwright
root=str(Path(__file__).resolve().parents[1])
class Handler(SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=root))
Thread(target=server.serve_forever,daemon=True).start()
origin='http://127.0.0.1:'+str(server.server_port)
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 context=b.new_context();page=context.new_page()
 page.goto(origin+'/');page.evaluate('navigator.serviceWorker.ready.then(()=>true)');page.reload();page.wait_for_function('navigator.serviceWorker.controller !== null')
 for path in ['index.html','en.html','legal.html?lang=en','gps-ai-demo.html?lang=en','fret-alerts-demo.html?lang=en']:
  page.goto(origin+'/'+path)
 context.set_offline(True)
 for path in ['index.html','en.html','legal.html?lang=en','gps-ai-demo.html?lang=en','fret-alerts-demo.html?lang=en']:
  response=page.goto(origin+'/'+path);assert response.status==200,(path,response.status)
  assert page.locator('html').get_attribute('lang')==('fr' if path=='index.html' else 'en')
 page.evaluate("caches.open('mamourart-v5').then(c=>c.delete(location.origin+'/gps-ai-demo.html'))")
 response=page.goto(origin+'/gps-ai-demo.html?lang=en');assert response.status==503
 assert 'unavailable offline' in page.locator('h1').inner_text()
 context.set_offline(False)
 response=page.goto(origin+'/gps-ai-demo.html?lang=en');assert response.status==200
 print('PASS real Chromium SW: 5 offline documents, EN continuity, missing demo 503, online recovery')
 for width in [320,390,768,1440]:
  page.set_viewport_size({'width':width,'height':900})
  for name in ['index.html','en.html','gps-ai-demo.html?lang=en','fret-alerts-demo.html?lang=en','legal.html?lang=en#privacy-en']:
   page.goto(origin+'/'+name)
   assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),(width,name)
   if name in ['index.html','en.html']:
    assert page.locator('h1').inner_text().startswith('Custom' if name=='en.html' else 'Des logiciels')
    assert page.locator('form').get_attribute('action')=='contact-submit.php'
    if width<=768:
     page.locator('#menuToggle').click();assert page.locator('#menuToggle').get_attribute('aria-expanded')=='true'
     page.keyboard.press('Escape');assert page.locator('#menuToggle').get_attribute('aria-expanded')=='false'
    page.locator('#enButton' if name=='index.html' else '#frButton').click()
    page.wait_for_url('**/en.html' if name=='index.html' else origin+'/')
   else: assert page.locator('html').get_attribute('lang')=='en',name
 print('PASS 20 page/viewport combinations, menu and FR/EN URL navigation')
 for width,name in [(1440,'index.html'),(390,'en.html')]:
  page.set_viewport_size({'width':width,'height':1000});page.goto(origin+'/'+name)
  page.wait_for_timeout(700)
  page.screenshot(path=f'/tmp/mission38-{width}.png',full_page=True)
 b.close()
server.shutdown()
