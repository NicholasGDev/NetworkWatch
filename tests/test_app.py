import io
from contextlib import closing
import json
import socket
import struct
import smtplib
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from app import create_app
from app.email import SMTPEmailSender
from app.models import History
from app.services import CaptureService, ClaudeVisionClient, FallbackVision, GeminiVisionClient, GitHubModelsVisionClient, VisionClient, UserError

class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.history = History(Path(self.tmp.name) / 'test.db')
        self.vision = SimpleNamespace(key='fake-key', model='test-model', answer=lambda png: 'Resposta')
        self.service = CaptureService(self.history, self.vision, lambda: b'fake-png')
        self.app = create_app(self.service, 'test-token')
        self.client = self.app.test_client()
        self.base = 'http://127.0.0.1'
    def tearDown(self):
        self.wait()
        self.tmp.cleanup()
    def wait(self):
        deadline = time.monotonic() + 3
        while self.service.lock.locked() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.service.lock.locked())
    def login(self):
        result = self.client.get('/bootstrap?token=test-token', base_url=self.base)
        self.assertEqual(result.status_code, 302)
        with self.client.session_transaction(base_url=self.base) as session:
            return {'X-CSRF-Token': session['csrf']}
    def test_unauthorized_history(self):
        self.assertEqual(self.client.get('/api/state', base_url=self.base).status_code, 401)
    def test_token_single_use_and_host(self):
        self.assertEqual(self.client.get('/bootstrap?token=wrong', base_url=self.base).status_code, 403)
        self.login()
        self.assertEqual(self.client.get('/bootstrap?token=test-token', base_url=self.base).status_code, 403)
        self.assertEqual(self.client.get('/api/state', base_url='http://evil.example').status_code, 403)
    def test_csrf_and_pause(self):
        headers = self.login()
        self.assertEqual(self.client.post('/api/pause', json={'paused': True}, base_url=self.base).status_code, 403)
        result = self.client.post('/api/pause', json={'paused': True}, headers=headers, base_url=self.base)
        self.assertTrue(result.json['paused'])
        self.assertFalse(self.service.trigger())
        self.assertEqual(self.history.list(), [])
    def test_complete_flow(self):
        self.assertTrue(self.service.trigger())
        self.wait()
        self.login()
        result = self.client.get('/api/state', base_url=self.base)
        self.assertEqual(result.json['answers'][0]['answer'], 'Resposta')
        self.assertEqual(result.json['answers'][0]['status'], 'done')
        self.assertNotIn('fake-key', result.get_data(as_text=True))
        monitor = self.client.get('/', base_url=self.base).get_data(as_text=True)
        self.assertIn('NetWatch', monitor)
        self.assertIn('href="/app"', monitor)
        self.assertNotIn('ScrollAnswer', monitor)
        app_page = self.client.get('/app', base_url=self.base).get_data(as_text=True)
        self.assertIn('ScrollAnswer', app_page)
        self.assertIn('Voltar ao painel', app_page)
        self.assertEqual(self.client.get('/api/network', base_url=self.base).status_code, 503)
    def test_email_sent_after_successful_answer(self):
        sender = Mock()
        self.service.email_sender = sender
        self.assertTrue(self.service.trigger())
        self.wait()
        sender.send.assert_called_once_with('Resposta')
        self.assertEqual(self.history.list()[0]['email_status'], 'sent')
        self.assertEqual(self.history.list()[0]['answer'], 'Resposta')
    def test_email_failure_preserves_answer(self):
        self.service.email_sender = SimpleNamespace(send=Mock(side_effect=smtplib.SMTPAuthenticationError(535, b'password hidden')))
        self.assertTrue(self.service.trigger())
        self.wait()
        item = self.history.list()[0]
        self.assertEqual(item['status'], 'done')
        self.assertEqual(item['answer'], 'Resposta')
        self.assertEqual(item['email_status'], 'error')
        self.assertIn('SMTPAuthenticationError', item['email_error'])
        self.assertNotIn('password hidden', item['email_error'])
    def test_duplicate_blocked(self):
        release = threading.Event()
        self.vision.answer = lambda png: (release.wait(2), 'ok')[1]
        try:
            self.assertTrue(self.service.trigger())
            self.assertFalse(self.service.trigger())
        finally:
            release.set()
        self.wait()
        self.assertEqual(len(self.history.list()), 1)
    def test_missing_key_does_not_capture(self):
        self.vision.key = ''
        self.service.capture = lambda: self.fail('must not capture')
        self.assertFalse(self.service.trigger())
        self.assertEqual(self.history.list()[0]['status'], 'error')
    def test_capture_failure_releases_lock(self):
        def fail(): raise UserError('Janela indisponível')
        self.service.capture = fail
        self.assertFalse(self.service.trigger())
        self.assertFalse(self.service.lock.locked())
        self.assertEqual(self.history.list()[0]['answer'], 'Janela indisponível')
    def test_api_failure_releases_lock(self):
        def fail(png): raise UserError('Sem conexão')
        self.vision.answer = fail
        self.service.trigger()
        self.wait()
        self.assertEqual(self.history.list()[0]['answer'], 'Sem conexão')
    def test_restart_recovers_pending(self):
        self.history.create()
        restarted = History(self.history.path)
        self.assertEqual(restarted.list()[0]['status'], 'error')
    def test_restart_marks_unconfirmed_email(self):
        item_id = self.history.create()
        self.history.finish(item_id, 'done', 'Resposta')
        self.history.email_result(item_id, 'sending')
        restarted = History(self.history.path)
        self.assertEqual(restarted.list()[0]['email_status'], 'error')
        self.assertIn('não confirmada', restarted.list()[0]['email_error'])
    def test_existing_history_adds_email_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'old.db'
            with closing(sqlite3.connect(path)) as db:
                with db:
                    db.execute("CREATE TABLE answers (id INTEGER PRIMARY KEY, created TEXT NOT NULL, status TEXT NOT NULL, answer TEXT NOT NULL DEFAULT '')")
                    db.execute("INSERT INTO answers (created, status, answer) VALUES ('2026-01-01', 'done', 'antiga')")
            history = History(path)
            self.assertEqual(history.list()[0]['answer'], 'antiga')
            self.assertEqual(history.list()[0]['email_status'], 'disabled')
    def test_clear_preserves_pending(self):
        a = self.history.create()
        self.history.finish(a, 'done', 'answer')
        self.history.create()
        self.history.clear()
        self.assertEqual([r['status'] for r in self.history.list()], ['pending'])

class EmailTests(unittest.TestCase):
    def test_ssl_sends_only_answer(self):
        smtp = Mock()
        smtp.__enter__ = Mock(return_value=smtp)
        smtp.__exit__ = Mock(return_value=False)
        with patch('app.email.smtplib.SMTP_SSL', return_value=smtp) as connect:
            SMTPEmailSender('smtp.example', 465, 'sender@example.com', 'secret',
                'recipient@example.com').send('Resposta da IA')
        self.assertEqual(connect.call_args.args, ('smtp.example', 465))
        self.assertEqual(connect.call_args.kwargs['timeout'], 15)
        smtp.login.assert_called_once_with('sender@example.com', 'secret')
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message['To'], 'recipient@example.com')
        self.assertEqual(message.get_content(), 'Resposta da IA\n')
        self.assertNotIn('secret', message.as_string())

    def test_starttls_before_login(self):
        smtp = Mock()
        smtp.__enter__ = Mock(return_value=smtp)
        smtp.__exit__ = Mock(return_value=False)
        with patch('app.email.smtplib.SMTP', return_value=smtp):
            SMTPEmailSender('smtp.example', 587, 'user@example.com', 'secret',
                'recipient@example.com', security='starttls').send('Resposta')
        calls = [call[0] for call in smtp.method_calls]
        self.assertLess(calls.index('starttls'), calls.index('login'))

class VisionTests(unittest.TestCase):
    def test_request_and_response(self):
        def opener(req, timeout):
            payload = json.loads(req.data)
            self.assertEqual(timeout, 120)
            self.assertFalse(payload['store'])
            image = payload['input'][0]['content'][1]
            self.assertEqual(image['image_url'], 'data:image/png;base64,cG5n')
            return io.StringIO(json.dumps({'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '42'}]}]}))
        self.assertEqual(VisionClient('test', 'model', 'prompt', opener).answer(b'png'), '42')
    def test_http_error_is_sanitized(self):
        def opener(*args, **kwargs):
            raise urllib.error.HTTPError('url', 401, 'secret-key', {}, None)
        with self.assertRaisesRegex(UserError, 'Chave da API inválida'):
            VisionClient('secret-key', 'model', 'prompt', opener).answer(b'png')
    def test_empty_response(self):
        with self.assertRaisesRegex(UserError, 'não retornou texto'):
            VisionClient('key', 'model', 'prompt', lambda *a, **kw: io.StringIO('{}')).answer(b'png')
    def test_connection_error_shows_reason(self):
        def opener(*args, **kwargs):
            raise urllib.error.URLError(ConnectionRefusedError('recusada'))
        with self.assertRaisesRegex(UserError, 'ConnectionRefusedError: recusada'):
            VisionClient('key', 'model', 'prompt', opener).answer(b'png')

class FakeAnthropic:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []
    def __call__(self, **options):
        self.options = options
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))
        return self
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.reply

def claude_reply(text, stop_reason='end_turn'):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type='thinking', thinking=''), SimpleNamespace(type='text', text=text)])

class ClaudeTests(unittest.TestCase):
    def test_request_and_response(self):
        fake = FakeAnthropic(claude_reply('42'))
        self.assertEqual(ClaudeVisionClient('k', 'claude-opus-5-5', 'prompt', fake).answer(b'png'), '42')
        self.assertEqual(fake.options['max_retries'], 0)
        call = fake.calls[0]
        self.assertEqual(call['model'], 'claude-opus-5-5')
        self.assertEqual(call['fallbacks'], 'default')
        image = call['messages'][0]['content'][0]
        self.assertEqual(image['source'], {'type': 'base64', 'media_type': 'image/png', 'data': 'cG5n'})
    def test_refusal(self):
        fake = FakeAnthropic(claude_reply('', 'refusal'))
        with self.assertRaisesRegex(UserError, 'recusou'):
            ClaudeVisionClient('k', 'm', 'p', fake).answer(b'png')
    def test_connection_error(self):
        import anthropic, httpx2
        fake = FakeAnthropic(error=anthropic.APIConnectionError(request=httpx2.Request('POST', 'https://api.anthropic.com')))
        with self.assertRaisesRegex(UserError, 'Sem resposta da API do Claude'):
            ClaudeVisionClient('k', 'm', 'p', fake).answer(b'png')

class GeminiTests(unittest.TestCase):
    def test_request_and_response(self):
        def opener(req, timeout):
            self.assertEqual(timeout, 120)
            self.assertTrue(req.full_url.endswith('/models/gemini-flash-latest:generateContent'))
            self.assertEqual(req.get_header('X-goog-api-key'), 'k')
            payload = json.loads(req.data)
            self.assertEqual(payload['contents'][0]['parts'][0]['inline_data'], {'mime_type': 'image/png', 'data': 'cG5n'})
            return io.StringIO(json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
                {'text': 'pensando', 'thought': True}, {'text': '42'}]}}]}))
        self.assertEqual(GeminiVisionClient('k', 'gemini-flash-latest', 'prompt', opener).answer(b'png'), '42')
    def test_invalid_key(self):
        def opener(*args, **kwargs):
            raise urllib.error.HTTPError('url', 400, 'bad', {}, io.BytesIO(b'{"error": {"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}'))
        with self.assertRaisesRegex(UserError, 'Chave do Gemini inválida'):
            GeminiVisionClient('k', 'm', 'p', opener).answer(b'png')
    def test_model_not_found(self):
        def opener(*args, **kwargs):
            raise urllib.error.HTTPError('url', 404, 'nf', {}, io.BytesIO(b'{}'))
        with self.assertRaisesRegex(UserError, 'GEMINI_MODEL'):
            GeminiVisionClient('k', 'm', 'p', opener).answer(b'png')
    def test_blocked(self):
        opener = lambda *a, **kw: io.StringIO(json.dumps({'promptFeedback': {'blockReason': 'SAFETY'}}))
        with self.assertRaisesRegex(UserError, 'bloqueou'):
            GeminiVisionClient('k', 'm', 'p', opener).answer(b'png')

class DataFolderTests(unittest.TestCase):
    def test_migrates_legacy_data_without_overwriting(self):
        from backend import data_folder
        with tempfile.TemporaryDirectory() as tmp:
            legacy, new = Path(tmp) / 'ScrollAnswer', Path(tmp) / 'NetWatch'
            legacy.mkdir()
            (legacy / 'config.json').write_text('{"gemini_api_key": "x"}', encoding='utf-8')
            (legacy / 'history.sqlite3').write_bytes(b'db')
            self.assertEqual(data_folder({'LOCALAPPDATA': tmp}), new)
            self.assertEqual((new / 'config.json').read_text(encoding='utf-8'), '{"gemini_api_key": "x"}')
            self.assertEqual((new / 'history.sqlite3').read_bytes(), b'db')
            self.assertFalse((legacy / 'config.json').exists())
            (legacy / 'config.json').write_text('{}', encoding='utf-8')
            data_folder({'LOCALAPPDATA': tmp})
            self.assertIn('gemini_api_key', (new / 'config.json').read_text(encoding='utf-8'))

class NetworkTests(unittest.TestCase):
    def test_rates_and_history(self):
        from app.network import NetworkMonitor
        counters = iter([{'Ethernet': (0, 0), 'Loopback Pseudo-Interface 1': (0, 0)},
                         {'Ethernet': (1000, 5000), 'Loopback Pseudo-Interface 1': (9999, 9999)}])
        monitor = NetworkMonitor(counters=lambda: next(counters), targets=[])
        monitor.sample(now=0)
        monitor.sample(now=2)
        self.assertEqual(monitor.rates['Ethernet'], (5000 * 8 / 2, 1000 * 8 / 2))
        _, down, up = monitor.history[-1]
        self.assertEqual((down, up), (20000, 4000))  # loopback fica fora do total
    def test_probe(self):
        from app.network import NetworkMonitor
        import contextlib
        def connect(address, timeout):
            if address[0] == 'down':
                raise OSError('timeout')
            return contextlib.nullcontext()
        monitor = NetworkMonitor(counters=lambda: {}, connect=connect, targets=[('A', 'up', 443), ('B', 'down', 443)])
        monitor.probe()
        self.assertTrue(monitor.latency[0]['ok'])
        self.assertIsNotNone(monitor.latency[0]['ms'])
        self.assertEqual(monitor.latency[1], {'name': 'B', 'host': 'down', 'ms': None, 'ok': False})
    def test_snapshot_shape(self):
        from app.network import NetworkMonitor
        snap = NetworkMonitor(targets=[]).snapshot()
        for key in ('hostname', 'down_bps', 'up_bps', 'interfaces', 'latency', 'connections', 'history', 'observed', 'uptime'):
            self.assertIn(key, snap)
        self.assertEqual(set(snap['observed']), {'process', 'endpoints', 'error', 'capture_error'})
        self.assertFalse(any('loopback' in i['name'].lower() for i in snap['interfaces']))
        json.dumps(snap)
    def test_remote_endpoints_belong_to_active_process(self):
        from app.network import NetworkMonitor
        address = lambda ip, port: SimpleNamespace(ip=ip, port=port)
        conns = [
            SimpleNamespace(pid=42, type=socket.SOCK_STREAM, laddr=address('192.0.2.10', 50000),
                raddr=address('198.51.100.2', 443), status='ESTABLISHED'),
            SimpleNamespace(pid=42, type=socket.SOCK_DGRAM, laddr=address('0.0.0.0', 51000),
                raddr=(), status='NONE'),
            SimpleNamespace(pid=99, type=socket.SOCK_STREAM, laddr=address('192.0.2.10', 50001),
                raddr=address('203.0.113.2', 443), status='ESTABLISHED')]
        monitor = NetworkMonitor(targets=[], connections=lambda kind: conns, foreground=lambda: 42,
            group=lambda pid: ('game.exe', {pid}))
        with patch('app.network.psutil.net_if_addrs', return_value={
            'Ethernet': [SimpleNamespace(address='192.0.2.10', family=socket.AF_INET)]}):
            monitor.observe()
        monitor.on_packet('192.0.2.10', 51000, '198.51.100.3', 7777)
        monitor.on_packet('192.0.2.10', 52000, '203.0.113.3', 7777)
        ips = {item['ip'] for item in monitor.snapshot()['observed']['endpoints']}
        self.assertEqual(ips, {'198.51.100.2', '198.51.100.3'})
        self.assertEqual(monitor.snapshot()['observed']['process'], 'game.exe')
        monitor.foreground = lambda: 99
        monitor.observe()
        ips = {item['ip'] for item in monitor.snapshot()['observed']['endpoints']}
        self.assertEqual(ips, {'203.0.113.2'})
        monitor.foreground = lambda: 42
        monitor.group = lambda pid: ('netwatch.exe', set())
        monitor.observe()
        self.assertEqual(monitor.snapshot()['observed']['process'], 'game.exe')

    def test_endpoints_expire_after_30_seconds(self):
        from app.network import NetworkMonitor
        monitor = NetworkMonitor(targets=[])
        with patch('app.network.time.monotonic', return_value=100):
            monitor.endpoints[('UDP', '198.51.100.3', 7777)] = 100
            self.assertEqual(len(monitor.snapshot()['observed']['endpoints']), 1)
        with patch('app.network.time.monotonic', return_value=130):
            self.assertEqual(monitor.snapshot()['observed']['endpoints'], [])

    def test_unrelated_udp_socket_cannot_claim_packet(self):
        from app.network import NetworkMonitor
        address = lambda ip, port: SimpleNamespace(ip=ip, port=port)
        conns = [
            SimpleNamespace(pid=42, type=socket.SOCK_DGRAM, laddr=address('0.0.0.0', 51000), raddr=(), status='NONE'),
            SimpleNamespace(pid=99, type=socket.SOCK_DGRAM, laddr=address('0.0.0.0', 51000), raddr=(), status='NONE')]
        monitor = NetworkMonitor(targets=[], connections=lambda kind: conns, foreground=lambda: 42,
            group=lambda pid: ('game.exe', {pid}))
        with patch('app.network.psutil.net_if_addrs', return_value={
            'Ethernet': [SimpleNamespace(address='192.0.2.10', family=socket.AF_INET)]}):
            monitor.observe()
        monitor.on_packet('192.0.2.10', 51000, '198.51.100.3', 7777)
        self.assertEqual(monitor.snapshot()['observed']['endpoints'], [])

    def test_udp_ipv4_header_checks_protocol_length_and_fragments(self):
        from app.network import udp_ipv4_header
        header = bytearray(28)
        header[0] = 0x45
        header[9] = socket.IPPROTO_UDP
        header[12:16] = socket.inet_aton('192.0.2.10')
        header[16:20] = socket.inet_aton('198.51.100.3')
        struct.pack_into('!HH', header, 20, 51000, 7777)
        self.assertEqual(udp_ipv4_header(header), ('192.0.2.10', 51000, '198.51.100.3', 7777))
        self.assertIsNone(udp_ipv4_header(header[:27]))
        header[9] = socket.IPPROTO_TCP
        self.assertIsNone(udp_ipv4_header(header))
        header[9] = socket.IPPROTO_UDP
        header[6:8] = b'\x00\x01'
        self.assertIsNone(udp_ipv4_header(header))

class GitHubModelsTests(unittest.TestCase):
    def test_request_and_response(self):
        def opener(req, timeout):
            self.assertEqual(req.full_url, 'https://models.github.ai/inference/chat/completions')
            self.assertEqual(req.get_header('Authorization'), 'Bearer tok')
            payload = json.loads(req.data)
            self.assertEqual(payload['model'], 'openai/gpt-6-luna')
            self.assertEqual(payload['messages'][1]['content'][1]['image_url']['url'], 'data:image/png;base64,cG5n')
            return io.StringIO(json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': '42'}}]}))
        self.assertEqual(GitHubModelsVisionClient('tok', 'openai/gpt-6-luna', 'p', opener).answer(b'png'), '42')
    def test_rate_limit(self):
        def opener(*args, **kwargs):
            raise urllib.error.HTTPError('url', 429, 'rl', {}, None)
        with self.assertRaisesRegex(UserError, 'Limite gratuito do GitHub'):
            GitHubModelsVisionClient('tok', 'm', 'p', opener).answer(b'png')
    def test_missing_scope(self):
        def opener(*args, **kwargs):
            raise urllib.error.HTTPError('url', 403, 'no', {}, None)
        with self.assertRaisesRegex(UserError, 'models:read'):
            GitHubModelsVisionClient('tok', 'm', 'p', opener).answer(b'png')

class FallbackTests(unittest.TestCase):
    def client(self, name='X', key='k', model='m', result=None, error=None):
        def answer(png):
            if error:
                raise error
            return result
        return SimpleNamespace(name=name, key=key, model=model, answer=answer)
    def test_primary_ok(self):
        vision = FallbackVision(self.client(result='gemini'), self.client(error=AssertionError('não deve chamar')))
        self.assertEqual(vision.answer(b'png'), 'gemini')
    def test_falls_back_in_order(self):
        vision = FallbackVision(self.client('Gemini', error=UserError('cota')), self.client('OpenAI', error=UserError('rede')),
            self.client('Claude', model='claude-opus-5-5', result='claude'))
        result = vision.answer(b'png')
        self.assertTrue(result.startswith('claude'))
        self.assertIn('Gemini: cota; OpenAI: rede', result)
    def test_all_fail(self):
        vision = FallbackVision(self.client('Gemini', error=UserError('A')), self.client('OpenAI', error=UserError('B')))
        with self.assertRaisesRegex(UserError, 'Gemini: A\nOpenAI: B'):
            vision.answer(b'png')
    def test_only_one_key(self):
        vision = FallbackVision(self.client('Gemini', model='g', error=UserError('A')), self.client(key='', error=AssertionError('não deve chamar')))
        self.assertTrue(vision.key)
        self.assertEqual(vision.model, 'g')
        with self.assertRaisesRegex(UserError, '^A$'):
            vision.answer(b'png')
    def test_no_keys(self):
        vision = FallbackVision(self.client(key=''), self.client(key=''))
        self.assertFalse(vision.key)

if __name__ == '__main__':
    unittest.main()
