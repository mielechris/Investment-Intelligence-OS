import json
import unittest
from unittest.mock import patch, MagicMock

from provider_gateway_credentials import SecretMaterial
from provider_gateway_transport import NativeHTTPS, Response, exchange
from test_provider_gateway_credentials import FAKE
from test_provider_gateway_live_contract import admitted, NOW


def snapshot():
    return {'MU': {'latestQuote': {'bp': 99, 'ap': 101, 't': NOW}, 'latestTrade': {'p': 100, 't': NOW}}}


class FakeNetwork:
    def __init__(self, payload=None, status=200, failure=False, raw=None):
        self.payload = snapshot() if payload is None else payload
        self.status, self.failure, self.raw = status, failure, raw
        self.calls = 0
        self.host = None

    def exchange(self, **kwargs):
        self.calls += 1
        self.host = kwargs['host']
        # Never retain authentication, URL or arguments in mock diagnostics.
        if self.failure:
            raise TimeoutError(FAKE.decode())
        return Response(self.status, self.raw if self.raw is not None else json.dumps(self.payload).encode())


class TransportTests(unittest.TestCase):
    def run_exchange(self, network, provider='ALPACA'):
        material = SecretMaterial([FAKE, FAKE] if provider == 'ALPACA' else [FAKE])
        try:
            return exchange(admitted(provider), material, network=network, now=NOW)
        finally:
            material.close()

    def test_all_five_hosts_use_one_exchange(self):
        from provider_gateway_live_contract import ROUTES
        for provider, route in ROUTES.items():
            fake = FakeNetwork(payload={})
            result = self.run_exchange(fake, provider)
            self.assertEqual(fake.calls, 1)
            self.assertEqual(fake.host, route[1])
            self.assertEqual(result['status'], 200)

    def test_redirect_and_error_no_retry(self):
        for status in (301, 302, 401, 403, 429, 500):
            fake = FakeNetwork(status=status)
            result = self.run_exchange(fake)
            self.assertEqual(fake.calls, 1)
            self.assertEqual(result['status'], status)
            self.assertIsNone(result['body'])

    def test_timeout_sanitized_no_retry(self):
        fake = FakeNetwork(failure=True)
        result = self.run_exchange(fake)
        self.assertEqual(fake.calls, 1)
        self.assertNotIn(FAKE.decode(), json.dumps(result))
        self.assertIsNone(result['body'])

    def test_raw_and_unicode_escaped_echo_rejected_before_hash(self):
        escaped = ''.join('\\u%04x' % byte for byte in FAKE)
        for raw in (json.dumps({'message': FAKE.decode()}).encode(), ('{"name":"' + escaped + '"}').encode()):
            result = self.run_exchange(FakeNetwork(raw=raw))
            self.assertIsNone(result['body'])
            self.assertNotIn(FAKE.decode(), repr(result))

    def test_sensitive_fields_nan_duplicate_keys_and_oversize_rejected(self):
        for raw in (b'{"api_key":"not_a_real_value"}', b'{"x":NaN}', b'{"MU":{},"MU":{}}', b' ' * 100001):
            self.assertIsNone(self.run_exchange(FakeNetwork(raw=raw))['body'])

    def test_offline_cannot_call_native(self):
        with self.assertRaises(ValueError):
            self.run_exchange(NativeHTTPS())

    def test_native_tls_hostname_and_cleanup_with_mocked_socket(self):
        import ssl
        ctx, sock, conn, response = MagicMock(), MagicMock(), MagicMock(), MagicMock()
        ctx.verify_mode, ctx.check_hostname = ssl.CERT_REQUIRED, True
        ctx.wrap_socket.return_value = sock
        conn.getresponse.return_value = response
        response.status = 200
        response.getheader.side_effect = lambda key, default: {'Content-Type': 'application/json'}.get(key, default)
        response.read1.side_effect = [b'{}', b'']
        with patch('provider_gateway_transport.ssl.create_default_context', return_value=ctx), patch('provider_gateway_transport.socket.socket', return_value=sock), patch('provider_gateway_transport.http.client.HTTPSConnection', return_value=conn):
            result = NativeHTTPS().exchange(host='data.alpaca.markets', address='192.0.2.1', method='GET', target='/v2/stocks/snapshots', headers={}, body=None, tls_file='synthetic.pem', timeout=5, limit=100)
        self.assertEqual(result.body, b'{}')
        ctx.wrap_socket.assert_called_once_with(sock, server_hostname='data.alpaca.markets')
        sock.connect.assert_called_once_with(('192.0.2.1', 443))
        conn.close.assert_called_once()
        sock.close.assert_called_once()

    def test_native_invalid_tls_before_socket(self):
        ctx = MagicMock(check_hostname=False)
        with patch('provider_gateway_transport.ssl.create_default_context', return_value=ctx), patch('provider_gateway_transport.socket.socket') as socket_factory:
            with self.assertRaises(ValueError):
                NativeHTTPS().exchange(host='data.alpaca.markets', address='192.0.2.1', method='GET', target='/v2/stocks/snapshots', headers={}, body=None, tls_file='synthetic.pem', timeout=5, limit=100)
            socket_factory.assert_not_called()

    def test_absolute_deadline_covers_slow_header_reads(self):
        from provider_gateway_transport import DeadlineReader
        sock = MagicMock()
        left = MagicMock(side_effect=[1, TimeoutError('DEADLINE')])
        reader = DeadlineReader(sock, left)
        with self.assertRaises(TimeoutError):
            reader.readinto(bytearray(10))
        sock.recv_into.assert_called_once()

    def test_native_route_rejected_before_tls_or_socket(self):
        with patch('provider_gateway_transport.ssl.create_default_context') as tls:
            with self.assertRaises(ValueError):
                NativeHTTPS().exchange(host='paper-api.alpaca.markets', address='192.0.2.1', method='GET', target='/v2/orders', headers={}, body=None, tls_file='synthetic.pem', timeout=5, limit=100)
            tls.assert_not_called()

    def test_native_connect_failure_closes_owned_socket(self):
        import ssl
        ctx, sock, conn = MagicMock(), MagicMock(), MagicMock()
        ctx.verify_mode, ctx.check_hostname = ssl.CERT_REQUIRED, True
        sock.connect.side_effect = TimeoutError('synthetic connect timeout')
        with patch('provider_gateway_transport.ssl.create_default_context', return_value=ctx), patch('provider_gateway_transport.socket.socket', return_value=sock), patch('provider_gateway_transport.http.client.HTTPSConnection', return_value=conn):
            with self.assertRaises(TimeoutError):
                NativeHTTPS().exchange(host='data.alpaca.markets', address='192.0.2.1', method='GET', target='/v2/stocks/snapshots', headers={}, body=None, tls_file='synthetic.pem', timeout=5, limit=100)
        conn.close.assert_called_once()
        sock.close.assert_called_once()

    def test_connection_close_does_not_truncate_unread_response(self):
        from provider_gateway_transport import DeadlineSocket
        sock = MagicMock()
        wrapper = DeadlineSocket(sock, lambda: 1)
        reader = wrapper.makefile('rb')
        wrapper.close()
        sock.close.assert_not_called()
        sock.recv_into.return_value = 0
        self.assertEqual(reader.read(), b'')
        reader.close()
        # The native exchange, not HTTPConnection's early detach, owns cleanup.
