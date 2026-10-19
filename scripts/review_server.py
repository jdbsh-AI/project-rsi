#!/usr/bin/env python3
"""Serve one frozen Project RSI review on a token-protected loopback URL.

This adapter processes local decisions and returns a receipt. It does not wake
an assistant conversation or launch a harness command. Use --once and let the
calling harness wait for the command to finish when that integration is needed.
"""
import argparse
import hmac
import json
import os
import secrets
import socketserver
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import project_rsi as rsi


BODY_LIMIT = 16 * 1024
FORM_LIMIT = 2 * 1024 * 1024
CSS = """
:root{color-scheme:light dark;--foreground:#18221f;--background:#fff;
--input:#bdc9c2;--muted:#596b61;--accent:#176744}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;padding:30px 20px 60px;background:#edf2ee;color:var(--foreground);
font:16px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:920px;margin:auto;padding:30px 36px;background:var(--background);
border:1px solid #d6dfd8;border-radius:16px}
h1,h2,h3{line-height:1.35}h3{margin:24px 0 12px}p{overflow-wrap:anywhere}
.text-small{font-size:14px;color:var(--muted)}
.form-check{display:inline-flex;align-items:center;gap:6px;margin:5px 18px 5px 0}
.form-check-input{accent-color:var(--accent);width:18px;height:18px}
.btn{font:inherit;padding:10px 18px;border:1px solid var(--input);border-radius:8px;
background:var(--background);color:var(--foreground);cursor:pointer}
.btn-primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn:disabled{opacity:.5;cursor:default}.viz-controls{display:flex;flex-wrap:wrap;gap:12px}
summary{cursor:pointer;color:var(--accent)}details{padding:10px 14px;background:#f3f6f3;
border-radius:8px}hr{border:0;border-top:1px solid var(--input);margin:24px 0}
pre{white-space:pre-wrap;overflow-wrap:anywhere}code{font-size:.9em}
@media(max-width:600px){body{padding:12px 8px 30px}main{padding:16px}.form-check{display:flex}}
@media(prefers-color-scheme:dark){:root{--foreground:#e3ece5;--background:#19241e;
--input:#526157;--muted:#bac9bd;--accent:#74c398}body{background:#101913}
main{border-color:#394b3e}details{background:#24352a}.btn-primary{color:#102519}}
"""


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def _read_regular(path, limit):
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular file required: ' + path.name)
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('file exceeds size limit: ' + path.name)
    return data


def _single_header(headers, name):
    values = headers.get_all(name, [])
    if len(values) != 1:
        return None
    return values[0]


def _equals(actual, expected):
    return isinstance(actual, str) and hmac.compare_digest(actual.encode('utf-8'), expected.encode('utf-8'))


class ReviewServer(HTTPServer):
    """A deliberately serial, single-run HTTP server bound only to IPv4 loopback."""

    allow_reuse_address = False
    request_queue_size = 4

    def server_bind(self):
        # HTTPServer normally reverse-resolves the bind address. This is a local
        # capability URL; DNS is unnecessary and can stall on CI/VPN networks.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def __init__(self, run, port=0, once=False, event_stream=None):
        raw_run = Path(run)
        if not raw_run.is_absolute() or raw_run.is_symlink():
            raise ValueError('run must be an absolute, non-symlink directory')
        self.run = raw_run.resolve(strict=True)
        if not self.run.is_dir():
            raise ValueError('run must be a directory')
        self.manifest_path = rsi.inside(self.run, 'manifest.json')
        self.binding_path = rsi.inside(self.run, 'form-binding.json')
        self.manifest_bytes = _read_regular(self.manifest_path, FORM_LIMIT)
        self.binding_bytes = _read_regular(self.binding_path, FORM_LIMIT)
        self.manifest = json.loads(self.manifest_bytes)
        self.binding = json.loads(self.binding_bytes)
        self.spec = self.binding.get('spec', {})
        manifest = self.manifest
        if manifest.get('schema') != 1 or not isinstance(manifest.get('thread_id'), str) or not manifest['thread_id'].strip():
            raise ValueError('manifest identity required')
        if manifest.get('application_adapter'):
            raise ValueError('project-specific application guard required; local server cannot bypass it')
        if self.spec.get('transport') != 'local' or manifest.get('transport') != 'local':
            raise ValueError('build a local-transport review before starting this server')
        if (self.spec.get('run') != str(self.run)
                or self.spec.get('form_id') != manifest.get('form_id')
                or self.spec.get('manifest_sha256') != rsi.digest(self.manifest_bytes)
                or self.spec.get('test_mode') is not bool(manifest.get('test_mode'))):
            raise ValueError('frozen form/run/version binding mismatch')
        self.submission_id = str(uuid.UUID(self.spec['submission_id']))
        if self.submission_id != self.spec['submission_id']:
            raise ValueError('canonical submission UUID required')
        self.form_path = Path(self.binding['output'])
        if not self.form_path.is_absolute():
            raise ValueError('frozen form output must be absolute')
        fragment = _read_regular(self.form_path, FORM_LIMIT)
        if rsi.digest(fragment) != self.binding.get('sha256'):
            raise ValueError('frozen form changed')
        self.document = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                         '<meta name="viewport" content="width=device-width,initial-scale=1">'
                         '<title>Project RSI review</title><style>' + CSS + '</style></head>'
                         '<body><main>' + fragment.decode('utf-8') + '</main></body></html>').encode('utf-8')
        self.token = secrets.token_urlsafe(32)
        self.once = once
        self.event_stream = event_stream if event_stream is not None else sys.stdout
        self.stop_requested = threading.Event()
        self.processed = False
        super().__init__(('127.0.0.1', port), ReviewHandler)
        self.timeout = 0.2
        self.authority = '127.0.0.1:' + str(self.server_port)
        self.origin = 'http://' + self.authority
        self.review_path = '/' + self.token + '/review'
        self.submit_path = '/' + self.token + '/submit'
        self.review_url = self.origin + self.review_path

    def event(self, kind, **fields):
        self.event_stream.write(json.dumps({'type': kind, **fields}, ensure_ascii=False) + '\n')
        self.event_stream.flush()

    def serve_review(self):
        self.event('review_server_started', review_url=self.review_url, run=str(self.run),
                   transport='local', test_mode=bool(self.manifest.get('test_mode')),
                   session_id=self.manifest['thread_id'], once=self.once,
                   conversation_wakeup=False)
        try:
            while not self.stop_requested.is_set() and not (self.once and self.processed):
                self.handle_request()
        finally:
            self.server_close()

    def stop(self):
        self.stop_requested.set()

    def check_frozen(self):
        if (_read_regular(self.manifest_path, FORM_LIMIT) != self.manifest_bytes
                or _read_regular(self.binding_path, FORM_LIMIT) != self.binding_bytes
                or rsi.digest(_read_regular(self.form_path, FORM_LIMIT)) != self.binding.get('sha256')):
            raise ValueError('frozen form or manifest changed; create a new run')

    def validate_submission(self, payload):
        required = {'schema', 'form_id', 'run', 'manifest_sha256', 'submission_id', 'answers'}
        if not isinstance(payload, dict) or set(payload) != required or type(payload['schema']) is not int or payload['schema'] != 1:
            raise ValueError('standard schema 1 submission required')
        for key in ('form_id', 'run', 'manifest_sha256', 'submission_id'):
            if payload[key] != self.spec[key]:
                raise ValueError('submission does not match this frozen form: ' + key)
        answers = payload['answers']
        if not isinstance(answers, list) or not all(isinstance(a, dict) for a in answers):
            raise ValueError('answers must be a list of decisions')
        expected = {item['id'] for item in self.manifest['items']}
        if len(answers) != len(expected) or {a.get('id') for a in answers} != expected:
            raise ValueError('one answer per item required')
        for answer in answers:
            if (set(answer) != {'id', 'value', 'comment'} or answer.get('value') not in rsi.CHOICES
                    or not isinstance(answer.get('comment'), str) or len(answer['comment']) > 2000):
                raise ValueError('invalid choice or comment')
            if answer['value'] in {'change', 'explain'} and not answer['comment'].strip():
                raise ValueError('comment required')

    def process_submission(self, data):
        self.check_frozen()
        payload = json.loads(data.decode('utf-8'))
        self.validate_submission(payload)
        acknowledgement_path = rsi.inside(self.run, 'acknowledgement.json')
        if acknowledgement_path.exists():
            previous = json.loads(_read_regular(acknowledgement_path, FORM_LIMIT))
            if previous.get('submission_id') != self.submission_id:
                raise ValueError('existing acknowledgement belongs to another submission')
            if previous.get('submission_sha256') != rsi.digest(data):
                raise ValueError('submission ID reused with different content')
        submission_path = rsi.inside(self.run, 'submissions/' + self.submission_id + '.json')
        submission_path.parent.mkdir(mode=0o700, exist_ok=True)
        try:
            fd = os.open(str(submission_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if _read_regular(submission_path, BODY_LIMIT) != data:
                raise ValueError('submission ID reused with different content')
        else:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        reference = 'Explicit local HTML submission to the token-bound Project RSI review server'
        receipt = rsi.consume(self.run, submission_path, reference, session_id=self.manifest['thread_id'])
        if receipt.get('status') not in {'ADOPTED_STATIC_ONLY', 'DECISIONS_RECORDED', 'PARTIAL_OR_CONFLICT'}:
            raise ValueError('receipt is incomplete; inspect the run before retrying')
        receipt_path = rsi.inside(self.run, 'receipts/' + self.submission_id + '.json')
        if not receipt_path.is_file():
            raise ValueError('consumer did not save its receipt')
        changed_paths = [change['path'] for change in receipt.get('changes', [])]
        acknowledgement = {
            'schema': 1, 'submission_id': self.submission_id,
            'thread_id': self.manifest['thread_id'], 'session_id': self.manifest['thread_id'],
            'processed': True, 'status': receipt['status'], 'transport': 'local',
            'conversation_wakeup': False, 'test_mode': bool(self.manifest.get('test_mode')),
            'scope': {'run': str(self.run), 'project_root': self.manifest['project_root']},
            'submission_file': str(submission_path), 'submission_sha256': rsi.digest(data),
            'receipt_file': str(receipt_path), 'changed_paths': changed_paths,
            'processed_at': datetime.now(timezone.utc).isoformat(),
        }
        if not acknowledgement_path.exists():
            rsi.atomic(acknowledgement_path, rsi.encoded(acknowledgement))
        self.processed = True
        self.event('submission_processed', submission_file=str(submission_path),
                   receipt_file=str(receipt_path), acknowledgement_file=str(acknowledgement_path),
                   status=receipt['status'], changed_paths=changed_paths,
                   test_mode=bool(self.manifest.get('test_mode')),
                   thread_id=self.manifest['thread_id'], duplicate=bool(receipt.get('duplicate')),
                   conversation_wakeup=False)
        return receipt


class ReviewHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    server_version = 'ProjectRSI'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(5)
        self.request_body_handled = False

    def log_message(self, format, *args):
        # Avoid emitting token-bearing URLs or personal decision text in logs.
        pass

    def discard_rejected_body(self):
        """Bounded cleanup before closing a rejected POST, never a submission.

        Closing with a queued body can abort the connection on Windows before
        the client receives its rejection status. This only discards bytes;
        guards still reject the request and the connection is never reused.
        """
        if self.command != 'POST' or self.request_body_handled:
            return
        self.request_body_handled = True
        value = _single_header(self.headers, 'Content-Length')
        amount = BODY_LIMIT + 1
        if value and len(value) <= 8 and value.isascii() and value.isdecimal():
            amount = min(int(value), amount)
        if not amount:
            return
        timeout = self.connection.gettimeout()
        try:
            self.connection.settimeout(1)
            self.rfile.read(amount)
        except (OSError, TimeoutError):
            pass
        finally:
            self.connection.settimeout(timeout)

    def respond(self, code, data, content_type='application/json; charset=utf-8'):
        if code >= 400:
            self.discard_rejected_body()
        if not isinstance(data, bytes):
            data = _json_bytes(data)
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(data)

    def request_guard(self, post=False):
        if _single_header(self.headers, 'Host') != self.server.authority:
            self.respond(403, {'error': 'untrusted Host'})
            return False
        origins = self.headers.get_all('Origin', [])
        if ((post and len(origins) != 1) or len(origins) > 1
                or (origins and not _equals(origins[0], self.server.origin))):
            self.respond(403, {'error': 'same-origin request required'})
            return False
        fetch_sites = self.headers.get_all('Sec-Fetch-Site', [])
        if len(fetch_sites) > 1 or (fetch_sites and fetch_sites[0] not in {'same-origin', 'none'}):
            self.respond(403, {'error': 'cross-site request rejected'})
            return False
        return True

    def do_GET(self):
        if not self.request_guard():
            return
        if not _equals(self.path, self.server.review_path):
            self.respond(404, {'error': 'unknown review URL'})
            return
        try:
            self.server.check_frozen()
        except (ValueError, OSError) as error:
            self.respond(409, {'error': str(error)})
            return
        self.respond(200, self.server.document, 'text/html; charset=utf-8')

    def do_POST(self):
        if not self.request_guard(post=True):
            return
        if not _equals(self.path, self.server.submit_path):
            self.respond(404, {'error': 'unknown submission URL'})
            return
        content_type = _single_header(self.headers, 'Content-Type')
        content_parts = [part.strip().lower() for part in (content_type or '').split(';')]
        if content_parts[0] != 'application/json' or any(part not in {'charset=utf-8', 'charset="utf-8"'} for part in content_parts[1:]):
            self.respond(415, {'error': 'application/json with UTF-8 required'})
            return
        length_value = _single_header(self.headers, 'Content-Length')
        if (self.headers.get_all('Transfer-Encoding', []) or length_value is None
                or len(length_value) > 8 or not length_value.isascii() or not length_value.isdecimal()):
            self.respond(400, {'error': 'one valid Content-Length required; transfer encoding is unsupported'})
            return
        length = int(length_value)
        if length < 1 or length > BODY_LIMIT:
            self.respond(413, {'error': 'submission must be between 1 byte and 16 KiB'})
            return
        try:
            self.request_body_handled = True
            data = self.rfile.read(length)
        except TimeoutError:
            self.respond(408, {'error': 'request body timed out'})
            return
        if len(data) != length:
            self.respond(400, {'error': 'incomplete request body'})
            return
        try:
            receipt = self.server.process_submission(data)
        except (ValueError, OSError, TypeError, KeyError) as error:
            self.respond(409, {'error': str(error)})
            return
        self.respond(200, receipt)

    def do_OPTIONS(self):
        # No CORS capability or preflight endpoint is exposed.
        self.respond(405, {'error': 'cross-origin access is unsupported'})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--once', action='store_true', help='exit after one processed submission')
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('port must be between 0 and 65535')
    try:
        server = ReviewServer(args.run, port=args.port, once=args.once)
        server.serve_review()
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, 'Project RSI review server: ' + str(error) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
