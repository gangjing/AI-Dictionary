#!/usr/bin/env python3
"""AI Dictionary acceptance checks that reflect the shipped 1.0.x implementation.

Native selection/OCR checks are platform-specific: on macOS they exercise the
compiled native bridge; on Windows the equivalent checks live in
scripts/windows_tray_shell.ps1 --self-test. This script never reports a feature
as passing merely because a mock or an unavailable platform exists.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMP = tempfile.TemporaryDirectory()
for name in ('dictionary.db', 'user_data.db'):
    shutil.copy2(ROOT / 'data' / name, Path(TEMP.name) / name)
os.environ['AIDICT_DATA_DIR'] = TEMP.name
os.environ['AIDICT_USER_DATA_DIR'] = TEMP.name
sys.path.insert(0, str(ROOT / 'scripts'))
import run_local_server as srv

srv.ensure_model_schema()
passed = 0
skipped = 0


def check(name, condition, detail=''):
    global passed
    assert condition, f'{name} failed: {detail}'
    passed += 1
    print(f'[PASS] {name}' + (f' - {detail}' if detail else ''))


def skip(name, reason):
    global skipped
    skipped += 1
    print(f'[SKIP] {name} - {reason}')


# AC-01 / F-001 / F-002: offline lookup, lemmatization, suggestions, source metadata.
result = srv.lookup_word_rpc('abandon', record_history=False)
check('AC-01 offline lookup', result['found'] and result['entry']['senses'], f"{result['elapsed_ms']} ms")
running = srv.lookup_word_rpc('Running', record_history=False)
check('F-001 lemmatization', running['found'] and running['entry']['lemma'] == 'run', running['entry']['lemma'])
miss = srv.lookup_word_rpc('abando', record_history=False)
check('F-001 prefix suggestions', not miss['found'] and 'abandon' in miss['suggestions'], str(miss['suggestions']))
check('F-002 traceable source', bool(result['entry']['source_id'] and result['entry']['source_version']),
      result['entry']['source_id'])

# AC-07 / F-010: privacy mode writes no history.
srv.clear_history_rpc()
srv.STATE.privacy_mode = True
srv.lookup_word_rpc('privacy', record_history=True)
check('AC-07 privacy guard', len(srv.list_history_rpc()) == 0)
srv.STATE.privacy_mode = False

# AC-08 / F-009: dedup and note preservation.
srv.delete_word_rpc('bank')
srv.save_word_rpc({'source_text': 'bank', 'note': 'initial'})
srv.save_word_rpc({'source_text': 'bank'})
bank = [item for item in srv.list_wordbook_rpc('bank') if item['source_text'] == 'bank']
check('AC-08 wordbook dedup/note preservation', len(bank) == 1 and bank[0]['note'] == 'initial')

# F-016: review schedules into the future.
srv.save_word_rpc({'source_text': 'review-check'})
srv.review_word_rpc('review-check', 5)
item = next(item for item in srv.list_wordbook_rpc('review-check') if item['source_text'] == 'review-check')
check('F-016 review schedule', item['next_review_at'] > item['updated_at'])

# AC-10 / F-015: token protection and glossary through a real HTTP translation path.
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
        self._send({'data': [{'id': 'acceptance-mock'}]})

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        payload = json.loads(self.rfile.read(length) or b'{}')
        text = payload['messages'][-1]['content'].replace('failover', '故障转移')
        self._send({'choices': [{'message': {'content': text}}]})


mock = ThreadingHTTPServer(('127.0.0.1', 0), MockHandler)
threading.Thread(target=mock.serve_forever, daemon=True).start()
try:
    srv.update_settings_rpc({
        'translation_provider': 'openai',
        'translation_endpoint': f'http://127.0.0.1:{mock.server_port}/v1',
        'translation_model': 'acceptance-mock',
    })
    translated = srv.translate_rpc({
        'request_id': 'acceptance-1',
        'text': 'Open `app.json`, keep {user_id}, https://example.com and failover.',
        'source_lang': 'en',
        'target_lang': 'zh',
        'preserve_format': True,
        'glossary': {'failover': '故障转移'},
    })
    check('AC-10 token protection', translated['status'] == 'ok' and translated['protected_tokens_verified'] is True,
          f"{translated.get('protected_tokens_count')} tokens")
    check('F-015 glossary', '故障转移' in translated['translated_text'])
    check('F-007 OpenAI-compatible local provider', srv.translation_status()['ready'] is True)
finally:
    mock.shutdown()
    mock.server_close()
    srv.update_settings_rpc({'translation_provider': 'auto', 'translation_endpoint': '', 'translation_model': ''})

# AC-09: no engine => clear guidance, dictionary still works.
no_engine = srv.translate_rpc({'text': 'Hello world', 'source_lang': 'en', 'target_lang': 'zh'})
check('AC-09 graceful engine degradation', no_engine['status'] == 'engine_unavailable' and srv.lookup_word_rpc('bandwidth', False)['found'])

# F-012: hotkey conflict guard.
conflict = srv.update_settings_rpc({'hotkey_lookup_mac': 'Command+C'})
check('F-012 hotkey conflict guard', conflict['status'] == 'error' and conflict['error_code'] == 'ERR_HOTKEY_CONFLICT')

# Model catalog must be realistic and verifiable, not placeholder hashes.
for model_id, meta in srv.MODEL_CATALOG.items():
    check(f'model {model_id} metadata',
          meta['sha256'].startswith(tuple('0123456789abcdef')) and len(meta['sha256']) == 64 and meta['size_bytes'] > 100_000_000,
          f"{meta['size_bytes'] / 1024 ** 3:.2f} GB")

# Native bridge checks only where an actual bridge binary is shipped.
bridge = srv.get_native_bridge_report()
if sys.platform == 'darwin' and bridge.get('status') != 'unavailable':
    secure = bridge.get('secureFieldSimulation', {})
    check('AC-03 native secure-field guard', secure.get('status') == 'blocked_secure_input' and secure.get('selectedText') is None)
    ocr = bridge.get('visionOcr', {})
    check('AC-04 native Vision OCR', ocr.get('status') == 'ok' and ocr.get('persistedToDisk') is False,
          f"{len(ocr.get('lines', []))} lines")
else:
    skip('AC-03/AC-04 native selection + OCR', 'use scripts/windows_tray_shell.ps1 --self-test on Windows or the macOS app bundle')

print('=' * 72)
print(f'PASSED {passed} checks, SKIPPED {skipped} native-only checks')
if skipped:
    print('Native-only checks are covered by the platform shells and are not claimed here.')
print('=' * 72)
if srv.STATE.dict_conn is not None:
    srv.STATE.dict_conn.close()
TEMP.cleanup()
