#!/usr/bin/env python3
"""Actual loopback HTTP tests against synthetic project files only."""
import copy
import http.client
import io
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import project_rsi as rsi
import review_server
from test_project_rsi import fixture


class ReviewHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='project-rsi-http-')
        self.base = Path(self.tmp.name).resolve()
        self.env = patch.dict(os.environ, {'CODEX_THREAD_ID': 'synthetic-thread'})
        self.env.start()
        self.root, self.run, self.payload = fixture(self.base)
        plan = rsi.read_json(self.run / 'plan.json')
        plan['transport'] = 'local'
        (self.run / 'plan.json').write_bytes(rsi.encoded(plan))
        (self.run / 'manifest.json').unlink()
        rsi.build(self.run / 'plan.json', self.run / 'form.html', session_id='synthetic-thread')
        binding = rsi.read_json(self.run / 'form-binding.json')['spec']
        self.payload.update(manifest_sha256=binding['manifest_sha256'], submission_id=binding['submission_id'])
        self.payload['answers'][2]['comment'] = (
            '请把本条建议写得更短一些，同时保留边界和适用条件。' * 20
            + '\n第二行备注必须完整保留，不能直接批准这项修改。'
        )
        self.original = (self.root / 'AGENTS.md').read_bytes()
        self.server = None
        self.thread = None

    def tearDown(self):
        if self.server is not None:
            self.server.stop()
            if self.thread is not None:
                self.thread.join(timeout=6)
                self.assertFalse(self.thread.is_alive())
            else:
                self.server.server_close()
        self.env.stop()
        self.tmp.cleanup()

    def start(self, once=False):
        self.events = io.StringIO()
        self.server = review_server.ReviewServer(self.run, once=once, event_stream=self.events)
        self.thread = threading.Thread(target=self.server.serve_review, daemon=True)
        self.thread.start()
        return self.server

    def request(self, method='POST', path=None, data=None, headers=None, origin=True):
        server = self.server
        if path is None:
            path = server.submit_path if method == 'POST' else server.review_path
        if data is None and method == 'POST':
            data = rsi.encoded(self.payload)
        request_headers = {}
        if method == 'POST':
            request_headers['Content-Type'] = 'application/json'
            if origin:
                request_headers['Origin'] = server.origin
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            connection.request(method, path, body=data, headers=request_headers)
            response = connection.getresponse()
            body = response.read()
            return response.status, dict(response.getheaders()), body
        finally:
            connection.close()

    def test_get_wraps_frozen_form_and_exposes_no_cors(self):
        server = self.start()
        status, headers, body = self.request('GET')
        self.assertEqual(status, 200)
        self.assertIn(b'<!doctype html>', body)
        self.assertIn(b'width=device-width', body)
        self.assertIn(b'project-rsi-', body)
        self.assertIn('text/html', headers['Content-Type'])
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(server.server_address[0], '127.0.0.1')
        self.assertGreaterEqual(len(server.token), 40)

    def test_mixed_approval_rejection_long_note_and_acknowledgement(self):
        self.start()
        status, _, body = self.request()
        self.assertEqual(status, 200, body)
        receipt = json.loads(body)
        self.assertEqual(receipt['status'], 'ADOPTED_STATIC_ONLY')
        self.assertEqual([item['decision'] for item in receipt['items']],
                         ['ADOPTED_STATIC_ONLY', 'REJECTED', 'REVISION_REQUESTED'])
        self.assertEqual(receipt['items'][2]['comment'], self.payload['answers'][2]['comment'])
        self.assertIn('complete result', (self.root / 'AGENTS.md').read_text())
        self.assertFalse((self.root / '.agents/skills/learned-rejected').exists())
        self.assertFalse((self.root / '.agents/skills/learned-revised').exists())
        acknowledgement = rsi.read_json(self.run / 'acknowledgement.json')
        self.assertTrue(acknowledgement['processed'])
        self.assertTrue(acknowledgement['test_mode'])
        self.assertFalse(acknowledgement['conversation_wakeup'])
        self.assertEqual(acknowledgement['scope']['project_root'], str(self.root))
        self.assertEqual(acknowledgement['changed_paths'], ['AGENTS.md'])
        self.assertEqual(acknowledgement['thread_id'], 'synthetic-thread')
        self.assertEqual(Path(acknowledgement['submission_file']).read_bytes(), rsi.encoded(self.payload))
        self.assertEqual(rsi.read_json(Path(acknowledgement['receipt_file']))['submission_id'], self.payload['submission_id'])
        events = [json.loads(line) for line in self.events.getvalue().splitlines()]
        self.assertEqual(events[-1]['type'], 'submission_processed')
        self.assertFalse(events[-1]['conversation_wakeup'])

    def test_duplicate_is_idempotent_but_changed_payload_is_rejected(self):
        self.start()
        self.assertEqual(self.request()[0], 200)
        target = self.root / 'AGENTS.md'
        acknowledgement = self.run / 'acknowledgement.json'
        target_bytes = target.read_bytes()
        target_mtime = target.stat().st_mtime_ns
        acknowledgement_bytes = acknowledgement.read_bytes()
        acknowledgement_mtime = acknowledgement.stat().st_mtime_ns
        status, _, body = self.request()
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['duplicate'])
        self.assertEqual(target.read_bytes(), target_bytes)
        self.assertEqual(target.stat().st_mtime_ns, target_mtime)
        self.assertEqual(acknowledgement.read_bytes(), acknowledgement_bytes)
        self.assertEqual(acknowledgement.stat().st_mtime_ns, acknowledgement_mtime)
        self.payload['answers'][1]['value'] = 'approve'
        status, _, body = self.request()
        self.assertEqual(status, 409)
        self.assertIn('reused', json.loads(body)['error'])
        self.assertFalse((self.root / '.agents/skills/learned-rejected').exists())

    def test_host_origin_token_and_cross_site_guards(self):
        self.start()
        cases = [
            ('GET', None, {'Host': 'attacker.invalid'}, True, 403),
            ('GET', None, {'Origin': 'https://attacker.invalid'}, True, 403),
            ('GET', '/review', {}, True, 404),
            ('POST', None, {}, False, 403),
            ('POST', None, {'Origin': 'null'}, True, 403),
            ('POST', None, {'Origin': 'https://attacker.invalid'}, True, 403),
            ('POST', None, {'Sec-Fetch-Site': 'cross-site'}, True, 403),
            ('POST', '/wrong-token/submit', {}, True, 404),
        ]
        for method, path, headers, origin, expected in cases:
            with self.subTest(method=method, path=path, headers=headers):
                self.assertEqual(self.request(method, path, headers=headers, origin=origin)[0], expected)
        self.assertEqual((self.root / 'AGENTS.md').read_bytes(), self.original)
        self.assertFalse((self.run / 'submissions').exists())

    def test_duplicate_host_header_is_rejected(self):
        self.start()
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.putrequest('GET', self.server.review_path, skip_host=True)
            connection.putheader('Host', self.server.authority)
            connection.putheader('Host', self.server.authority)
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
        finally:
            connection.close()

    def test_content_type_oversize_and_transfer_encoding_rejected(self):
        self.start()
        for content_type in ['text/plain', 'application/x-www-form-urlencoded', 'application/json; charset=latin1']:
            with self.subTest(content_type=content_type):
                self.assertEqual(self.request(headers={'Content-Type': content_type})[0], 415)
        self.assertEqual(self.request(data=b'x' * (review_server.BODY_LIMIT + 1))[0], 413)
        self.assertEqual(self.request(headers={'Transfer-Encoding': 'chunked'})[0], 400)
        self.assertEqual((self.root / 'AGENTS.md').read_bytes(), self.original)
        self.assertFalse((self.run / 'submissions').exists())

    def test_payload_cannot_select_other_run_manifest_or_submission_id(self):
        self.start()
        for field, value in [('run', str(self.base / 'other-run')),
                             ('manifest_sha256', '0' * 64),
                             ('submission_id', '00000000-0000-4000-8000-000000000000'),
                             ('form_id', 'foreign-form')]:
            payload = copy.deepcopy(self.payload)
            payload[field] = value
            with self.subTest(field=field):
                self.assertEqual(self.request(data=rsi.encoded(payload))[0], 409)
        self.assertFalse((self.run / 'submissions').exists())
        self.assertEqual((self.root / 'AGENTS.md').read_bytes(), self.original)

    def test_invalid_choices_are_rejected_before_submission_file_is_created(self):
        self.start()
        payload = copy.deepcopy(self.payload)
        payload['answers'][2]['comment'] = ''
        status, _, body = self.request(data=rsi.encoded(payload))
        self.assertEqual(status, 409)
        self.assertIn('comment required', json.loads(body)['error'])
        self.assertFalse((self.run / 'submissions').exists())
        self.assertFalse((self.run / 'acknowledgement.json').exists())
        self.assertEqual((self.root / 'AGENTS.md').read_bytes(), self.original)

    def test_malformed_encoding_headers_and_non_ascii_origin_fail_cleanly(self):
        self.start()
        self.assertEqual(self.request(data=json.dumps(self.payload).encode('utf-16'))[0], 409)
        self.assertEqual(self.request(headers={'Content-Length': '9' * 5000})[0], 400)
        self.assertEqual(self.request(headers={'Origin': 'http://attacker.invalid/\u00ff'})[0], 403)
        self.assertEqual(self.request('GET')[0], 200)
        self.assertEqual((self.root / 'AGENTS.md').read_bytes(), self.original)
        self.assertFalse((self.run / 'submissions').exists())

    def test_existing_foreign_acknowledgement_blocks_before_writes(self):
        self.start()
        (self.run / 'acknowledgement.json').write_bytes(rsi.encoded({'submission_id': 'foreign'}))
        status, _, body = self.request()
        self.assertEqual(status, 409)
        self.assertIn('acknowledgement', json.loads(body)['error'])
        self.assertFalse((self.run / 'submissions').exists())
        self.assertEqual((self.root / 'AGENTS.md').read_bytes(), self.original)

    def test_frozen_manifest_change_is_rejected(self):
        self.start()
        path = self.run / 'manifest.json'
        path.write_bytes(path.read_bytes() + b' ')
        self.assertEqual(self.request('GET')[0], 409)
        self.assertEqual(self.request()[0], 409)
        self.assertFalse((self.run / 'submissions').exists())

    def test_project_application_guard_and_native_transport_refuse_start(self):
        manifest_path = self.run / 'manifest.json'
        manifest = rsi.read_json(manifest_path)
        manifest['application_adapter'] = {'plan': 'external-guard.json', 'sha256': '0' * 64}
        manifest_path.write_bytes(rsi.encoded(manifest))
        with self.assertRaisesRegex(ValueError, 'project-specific'):
            review_server.ReviewServer(self.run)
        del manifest['application_adapter']
        manifest['transport'] = 'native'
        manifest_path.write_bytes(rsi.encoded(manifest))
        with self.assertRaisesRegex(ValueError, 'local-transport'):
            review_server.ReviewServer(self.run)

    def test_local_server_uses_bound_session_instead_of_codex_environment(self):
        self.start()
        with patch.dict(os.environ, {'CODEX_THREAD_ID': 'unrelated-codex-thread'}):
            status, _, body = self.request()
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)['thread_id'], 'synthetic-thread')

    def test_loopback_startup_never_resolves_a_hostname(self):
        with patch('socket.getfqdn', side_effect=AssertionError('loopback server must not query DNS')):
            self.start()
            status, _, body = self.request('GET')
        self.assertEqual(status, 200, body)

    def test_once_process_returns_after_real_http_submission(self):
        command = [sys.executable, str(Path(review_server.__file__).resolve()),
                   '--run', str(self.run), '--once']
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8')
        lines = queue.Queue()
        reader = threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True)
        reader.start()
        try:
            try:
                first_line = lines.get(timeout=20)
            except queue.Empty:
                self.fail('server did not produce its startup event within 20 seconds; child status: '+str(process.poll()))
            self.assertTrue(first_line, 'server exited before startup event')
            event = json.loads(first_line)
            self.assertEqual(event['type'], 'review_server_started')
            url = urlsplit(event['review_url'])
            connection = http.client.HTTPConnection(url.hostname, url.port, timeout=5)
            try:
                connection.request('POST', url.path.rsplit('/', 1)[0] + '/submit',
                                   body=rsi.encoded(self.payload),
                                   headers={'Origin': url.scheme + '://' + url.netloc,
                                            'Content-Type': 'application/json'})
                response = connection.getresponse()
                body = response.read()
                self.assertEqual(response.status, 200, body)
            finally:
                connection.close()
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(stderr, '')
            processed_event = json.loads(stdout.strip())
            self.assertEqual(processed_event['type'], 'submission_processed')
            self.assertTrue(Path(processed_event['receipt_file']).is_file())
            self.assertTrue(Path(processed_event['acknowledgement_file']).is_file())
            self.assertFalse(processed_event['conversation_wakeup'])
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


if __name__ == '__main__':
    unittest.main()
