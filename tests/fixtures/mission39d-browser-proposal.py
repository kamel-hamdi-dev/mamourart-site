"""Integration proposal only; invoke with the absolute simulated tree path."""
import sys
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

def main():
    root = Path(sys.argv[1]).resolve()
    origin = 'https://mamourart-integration.test'
    checks = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        for blocked in (False, True):
            context = browser.new_context(service_workers='block')
            def route(request):
                url = urlsplit(request.request.url)
                if url.hostname != 'mamourart-integration.test':
                    request.abort(); return
                path = root / (url.path.lstrip('/') or 'index.html')
                if path.is_file() and path.resolve().is_relative_to(root): request.fulfill(path=str(path))
                else: request.fulfill(status=404, body='missing local fixture')
            context.route('**/*', route)
            if blocked:
                context.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new DOMException('disabled','SecurityError')}})")
            else:
                context.add_init_script("localStorage.setItem('mamourart-language-v2','fr')")
            page = context.new_page(); errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            for name, lang in [('index.html','fr'), ('en.html','en')]:
                for status in ('sent','error'):
                    page.goto(f'{origin}/{name}?contact_status={status}#quoteResult')
                    assert page.locator('html').get_attribute('lang') == lang
                    expected = ('Your request was sent.' if status == 'sent' else 'Your message could not be sent.') if lang=='en' else ('Votre demande a été envoyée.' if status=='sent' else "L'envoi n'a pas abouti.")
                    assert page.locator('#quoteResult').inner_text().startswith(expected)
                    assert page.locator('#quoteResult').evaluate('(e)=>document.activeElement===e')
                    assert page.locator('[name=name]').get_attribute('minlength') == '2'
                    assert page.locator('form').get_attribute('action') == 'contact-submit.php' + ('?lang=en' if lang=='en' else '')
                    checks += 1
            page.goto(origin+'/index.html?contact_status=sent#quoteResult')
            page.locator('#enButton').click(); page.wait_for_url('**/en.html?contact_status=sent#quoteResult')
            assert page.locator('html').get_attribute('lang')=='en'
            page.locator('#frButton').click(); page.wait_for_url(origin+'/?contact_status=sent#quoteResult')
            assert page.locator('html').get_attribute('lang')=='fr'; checks += 2
            assert not errors, errors
            context.close()
        browser.close()
    print(f'PASS {checks} Chromium language/status checks; storage available and unavailable; all requests intercepted locally; no submission')

if __name__ == '__main__':
    main()
