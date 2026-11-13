"""Theme persistence and layout checks across browser engines and pixel densities."""
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright
import test_regressions as regression

server = regression.srv.ThreadingHTTPServer(('127.0.0.1', 0), regression.srv.DictionaryRequestHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{server.server_port}'
output = Path(__file__).resolve().parent.parent / 'dist/test-results/ui'
output.mkdir(parents=True, exist_ok=True)
try:
    with sync_playwright() as p:
        for engine in ('chromium', 'webkit'):
            browser = getattr(p, engine).launch()
            for scale in (1, 1.25, 1.5, 2):
                context = browser.new_context(viewport={'width': 1120, 'height': 750}, device_scale_factor=scale)
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda err: errors.append(str(err)))
                page.goto(url)
                page.wait_for_function('currentEntry !== null')
                assert page.evaluate('devicePixelRatio') == scale
                assert not page.locator('#systemInfoBar').is_visible()
                assert page.locator('.viewport').evaluate('(x) => x.scrollWidth <= x.clientWidth')
                page.locator('#dictSearchInput').fill('brian')
                page.locator('#dictSearchInput').press('Enter')
                page.wait_for_function('currentEntry === null')
                assert page.locator('#dictMainColumn .empty-state').is_visible()
                page.screenshot(path=str(output / f'{engine}-{scale}-dark.png'))
                page.locator('#themeBtn').click()
                assert page.evaluate("getComputedStyle(document.documentElement).colorScheme") == 'light'
                page.reload()
                page.wait_for_function('currentEntry !== null')
                assert page.locator('body').evaluate("x => x.classList.contains('light-mode')")
                page.screenshot(path=str(output / f'{engine}-{scale}-light.png'))
                for width in (800, 1120):
                    page.set_viewport_size({'width': width, 'height': 750})
                    for name in ('dictionary', 'wordbook', 'history', 'models', 'translate', 'ocr'):
                        page.evaluate('(name) => switchTab(name)', name)
                        page.wait_for_timeout(60)
                        assert page.locator('.viewport').evaluate('(x) => x.scrollWidth <= x.clientWidth'), (engine, scale, width, name)
                        assert page.locator('header').evaluate('(x) => x.scrollWidth <= x.clientWidth'), (engine, scale, width, 'header')
                assert errors == [], errors
                context.close()
            browser.close()
    print('PASS: Chromium + WebKit; 100/125/150/200% rendering; dark/light persistence; 800/1120px layouts across six pages.')
finally:
    server.shutdown()
    server.server_close()
    if regression.srv.STATE.dict_conn:
        regression.srv.STATE.dict_conn.close()
    regression.TEMP.cleanup()
