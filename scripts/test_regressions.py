"""Regression checks against isolated databases and real Chromium/WebKit pages."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent.parent
TEMP = tempfile.TemporaryDirectory()
for name in ('dictionary.db', 'user_data.db'):
    shutil.copy2(ROOT / 'data' / name, Path(TEMP.name) / name)
os.environ['AIDICT_DATA_DIR'] = TEMP.name
os.environ['AIDICT_USER_DATA_DIR'] = TEMP.name
import run_local_server as srv


class BackendTests(unittest.TestCase):
    def test_lookup_and_quoted_chinese(self):
        self.assertEqual(srv.lookup_word_rpc('Running', False)['entry']['lemma'], 'run')
        self.assertFalse(srv.lookup_word_rpc('中文" OR "', False)['found'])

    def test_note_clear_preserve_and_reimport(self):
        payload = {'source_text': 'regression-word', 'note': 'remember'}
        srv.save_word_rpc(payload)
        self.assertEqual(srv.save_word_rpc({'source_text': 'regression-word'})['note'], 'remember')
        self.assertEqual(srv.save_word_rpc({**payload, 'note': ''})['note'], '')

    def test_non_mac_bridge(self):
        if os.sys.platform != 'darwin':
            self.assertEqual(srv.get_native_bridge_report()['status'], 'unavailable')

    def test_dictionary_reimport_updates_search_index(self):
        for text in ('独特旧释义甲', '独特新释义乙'):
            srv.import_custom_dictionary_rpc([{'word': 'regression-index', 'zh': text}])
        self.assertFalse(srv.lookup_word_rpc('独特旧释义甲', False)['found'])
        self.assertEqual(srv.lookup_word_rpc('独特新释义乙', False)['entry']['lemma'], 'regression-index')

    def test_review_scheduled_in_future(self):
        srv.save_word_rpc({'source_text': 'regression-review'})
        srv.review_word_rpc('regression-review', 5)
        item = next(x for x in srv.list_wordbook_rpc() if x['source_text'] == 'regression-review')
        self.assertGreater(item['next_review_at'], item['updated_at'])

    def test_no_fabricated_ai_translation(self):
        result = srv.translate_rpc({'text': 'A novel sentence', 'request_id': 'test'})
        self.assertEqual(result['status'], 'engine_unavailable')
        self.assertNotIn('translated_text', result)

    def test_http_invalid_json(self):
        for body in (b'{', b'[]', b'null'):
            req = urllib.request.Request(URL + '/api/settings', data=body)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.code, 400)
            ctx.exception.close()


class BrowserTests(unittest.TestCase):
    def test_browser_regressions(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            for engine in ('chromium', 'webkit'):
                with self.subTest(engine=engine):
                    browser = getattr(p, engine).launch()
                    page = browser.new_page(viewport={'width': 1120, 'height': 750})
                    errors = []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.goto(URL)
                    page.wait_for_function('currentEntry !== null')
                    # Emulate the native host's asynchronous showMainWindow -> switchTab callback.
                    page.evaluate('''() => {
                        window.nativeCalls = 0;
                        window.webkit = {messageHandlers: {nativeShell: {postMessage: m => {
                            if (m.action === 'showMainWindow') {
                                nativeCalls++;
                                if (nativeCalls < 20) queueMicrotask(() => window.switchTab(m.tab));
                            }
                        }}}};
                        restoreMainWindowFromTray('models');
                    }''')
                    page.wait_for_timeout(150)
                    self.assertEqual(page.evaluate('nativeCalls'), 1, 'native navigation feedback loop')
                    self.assertTrue(page.locator('#page-models').is_visible())
                    page.evaluate("window.switchTab('dictionary')")
                    original = page.evaluate('currentEntry.lemma')
                    page.evaluate("document.getElementById('trayMiniInput').value = 'run'; runTrayMiniQuery()")
                    page.wait_for_function("miniEntry && miniEntry.lemma === 'run'")
                    self.assertEqual(page.evaluate('currentEntry.lemma'), original)
                    # No HTML execution from lookup queries, including inline JavaScript quoting.
                    malicious = '<img src=x onerror="window.injected=1">'
                    page.locator('#dictSearchInput').fill(malicious)
                    page.evaluate('performLookup()')
                    page.wait_for_function('currentEntry === null')
                    self.assertIsNone(page.evaluate('window.injected'))
                    self.assertEqual(page.locator('#dictMainColumn img').count(), 0)
                    # Deliberately resolve lookups in reverse order.
                    page.evaluate('''async () => {
                        const realFetch = window.fetch;
                        const pending = [];
                        window.fetch = () => new Promise(resolve => pending.push(resolve));
                        dictSearchInput.value = 'old'; const old = performLookup();
                        dictSearchInput.value = 'new'; const fresh = performLookup();
                        pending[1]({json: async () => ({found:false,query:'new',suggestions:[]})}); await fresh;
                        pending[0]({json: async () => ({found:false,query:'old',suggestions:[]})}); await old;
                        window.fetch = realFetch;
                    }''')
                    self.assertIn('new', page.locator('#dictMainColumn').inner_text())
                    self.assertNotIn('old', page.locator('#dictMainColumn').inner_text())
                    # Cancel must invalidate an outstanding response even if the server already completed.
                    page.evaluate('''async () => {
                        const realFetch = window.fetch; let resolve;
                        window.fetch = () => new Promise(r => resolve = r);
                        transStudioInput.value = 'hello'; transStudioOutput.value = 'unchanged';
                        const running = runStudioTranslation();
                        window.fetch = realFetch;
                        await cancelStudioTranslation();
                        resolve({json: async () => ({status:'ok',translated_text:'STALE'})});
                        await running;
                    }''')
                    self.assertEqual(page.locator('#transStudioOutput').input_value(), 'unchanged')
                    for name in ('dictionary', 'translate', 'wordbook', 'history', 'models'):
                        page.evaluate('(name) => window.switchTab(name)', name)
                        page.wait_for_timeout(60)
                    out = ROOT / 'dist' / 'test-results'
                    out.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(out / f'{engine}-settings.png'))
                    self.assertEqual(errors, [])
                    browser.close()


if __name__ == '__main__':
    server = srv.ThreadingHTTPServer(('127.0.0.1', 0), srv.DictionaryRequestHandler)
    URL = f'http://127.0.0.1:{server.server_port}'
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        unittest.main(verbosity=2)
    finally:
        server.shutdown()
        server.server_close()
        if srv.STATE.dict_conn:
            srv.STATE.dict_conn.close()
        TEMP.cleanup()
