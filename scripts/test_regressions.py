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

    def test_model_download_sha256(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import hashlib
        import threading
        import time

        payload = b'model-bytes-' * 200000  # ~2.4 MB
        digest = hashlib.sha256(payload).hexdigest()

        class ModelHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = ThreadingHTTPServer(('127.0.0.1', 0), ModelHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        target = srv.models_dir() / 'regression-model.gguf'
        srv.MODEL_CATALOG['regression-model'] = {
            'file_name': target.name,
            'size_bytes': len(payload),
            'sha256': digest,
            'url': f'http://127.0.0.1:{server.server_port}/model.gguf',
        }
        conn = srv.get_user_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO model_registry
            (id, model_name, quant, file_path, sha256, size_bytes, recommended_ram_gb, license, status, is_active, installed_at)
            VALUES ('regression-model', 'Regression Model', 'Q4', ?, ?, ?, 4, 'Apache-2.0', 'not_installed', 0, NULL)
            """,
            (str(target), digest, len(payload)),
        )
        conn.commit()
        conn.close()
        try:
            srv.start_model_download('regression-model')
            deadline = time.time() + 30
            state = {}
            while time.time() < deadline:
                state = srv.get_download_status('regression-model')
                if state.get('status') in ('ready', 'error'):
                    break
                time.sleep(0.1)
            self.assertEqual(state.get('status'), 'ready', state)
            self.assertTrue(target.is_file())
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), digest)
        finally:
            server.shutdown()
            server.server_close()
            target.unlink(missing_ok=True)
            target.with_suffix(target.suffix + '.part').unlink(missing_ok=True)
            srv.MODEL_CATALOG.pop('regression-model', None)
            conn = srv.get_user_conn()
            conn.execute("DELETE FROM model_registry WHERE id = 'regression-model'")
            conn.commit()
            conn.close()

    def test_openai_compatible_translation_and_token_protection(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading

        class MockHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, payload):
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._send({'data': [{'id': 'mock-translator'}]})

            def do_POST(self):
                length = int(self.headers.get('Content-Length', '0'))
                payload = json.loads(self.rfile.read(length) or b'{}')
                text = payload['messages'][-1]['content']
                self._send({'choices': [{'message': {'content': '【译】' + text}}]})

        server = ThreadingHTTPServer(('127.0.0.1', 0), MockHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            srv.update_settings_rpc({
                'translation_provider': 'openai',
                'translation_endpoint': f'http://127.0.0.1:{server.server_port}/v1',
                'translation_model': 'mock-translator',
            })
            result = srv.translate_rpc({
                'request_id': 'mock-test',
                'text': 'Check `config.json`, {user_name} and https://example.com.',
                'source_lang': 'en',
                'target_lang': 'zh',
                'preserve_format': True,
                'glossary': {'failover': '故障转移'},
            })
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['provider'], 'openai')
            self.assertIn('`config.json`', result['translated_text'])
            self.assertIn('{user_name}', result['translated_text'])
            self.assertIn('https://example.com', result['translated_text'])
            self.assertTrue(result['protected_tokens_verified'])
            self.assertEqual(srv.translation_status()['ready'], True)
        finally:
            server.shutdown()
            server.server_close()
            srv.update_settings_rpc({
                'translation_provider': 'auto',
                'translation_endpoint': '',
                'translation_model': '',
            })


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

                    # Selection popup and OCR result receive paths used by the native shells.
                    page.evaluate("receiveSelection('ubiquitous', {source:'selection', app:'Test App', method:'uia'})")
                    page.wait_for_function("document.getElementById('trayMiniInput').value === 'ubiquitous'")
                    page.wait_for_function("document.getElementById('trayMiniResultBody').innerText.includes('ubiquitous')")
                    self.assertTrue(page.locator('#youdaoMiniPopover').is_visible())
                    self.assertEqual(page.locator('#trayMiniSource').inner_text(), '划词 · Test App')
                    page.evaluate("""() => receiveOcrResult({
                        status: 'ok', text: 'Hello OCR', lines: [{text: 'Hello OCR', left: 1, top: 2, width: 3, height: 4}],
                        language: 'zh-Hans-CN', elapsed_ms: 12, message: 'ok', width: 100, height: 40
                    })""")
                    page.evaluate("switchTab('ocr')")
                    self.assertEqual(page.locator('.ocr-line-input').count(), 1)
                    self.assertEqual(page.locator('.ocr-line-input').input_value(), 'Hello OCR')
                    self.assertIn('识别完成', page.locator('#ocrStatusBadge').inner_text())

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
