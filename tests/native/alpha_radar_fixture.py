"""Separate synthetic TLS fixture. Never resolves or contacts a provider."""
import json
import ssl
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from alpha_market_baseline import require
from provider_gateway_contract import utc
from alpha_radar_admission import SyntheticCapability, SCOPE


def response(cap, target):
    require(type(cap) is SyntheticCapability, 'SYNTHETIC_CAPABILITY_REQUIRED')
    p, r, _ = cap.recheck()
    route = urlsplit(target)
    require(not route.scheme and not route.netloc and not route.fragment, 'FIXTURE_ROUTE')
    fields = parse_qs(route.query, strict_parsing=True)
    require(set(fields) == {'at'} and len(fields['at']) == 1, 'FIXTURE_QUERY')
    slot_text = route.path.removeprefix('/slot/')
    require(route.path == '/slot/' + slot_text and slot_text.isdecimal(), 'FIXTURE_SLOT')
    slot = int(slot_text)
    require(0 <= slot < 475, 'FIXTURE_SLOT')
    row = p['plan']['rows'][slot]
    at = fields['at'][0]
    require(utc(row['valid_from']) <= utc(at) < utc(row['expires_at']), 'FIXTURE_WINDOW')
    scenarios = json.loads((Path(r['root']) / p['fixture']['responses']).read_bytes())
    require(set(scenarios) == {'scope', 'faults'} and scenarios['scope'] == SCOPE, 'FIXTURE_SCOPE')
    fault = scenarios['faults'].get(str(slot))
    body = {'endpoint': 'REALTIME_BULK_QUOTES', 'data': [
        {'symbol': symbol, 'timestamp': at, 'open': '100', 'high': '101',
         'low': '99', 'close': '100', 'volume': 1000} for symbol in row['symbols']]}
    if fault == 'missing':
        body['data'].pop()
    elif fault == 'duplicate':
        body['data'].append(dict(body['data'][0]))
    elif fault == 'unexpected':
        body['data'][0]['symbol'] = 'UNEXPECTED'
    elif fault == 'stale':
        body['data'][0]['timestamp'] = '2026-09-14T00:00:00+00:00'
    elif fault == 'malformed':
        return 200, b'{'
    elif fault == 'oversize':
        return 200, b' ' * 1_000_001
    elif fault == 'redirect':
        return 302, b''
    elif fault == 'throttle':
        return 429, b''
    elif fault == 'error':
        return 500, b''
    else:
        require(fault in (None, 'timeout', 'interrupt'), 'UNKNOWN_FIXTURE_FAULT')
    return 200, json.dumps(body, separators=(',', ':')).encode()


def emit(handler, status, data, *, fault, stop, monotonic=time.monotonic, pause=time.sleep):
    """Pinned fixture faults; injectable clocks are used only by offline tests."""
    if fault == 'timeout':
        deadline = monotonic() + 21
        while monotonic() < deadline and not stop():
            pause(min(.05, deadline - monotonic()))
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Content-Length', str(len(data)))
    handler.end_headers()
    handler.wfile.write(data[:-2] if fault == 'interrupt' else data)
    if fault == 'interrupt':
        handler.close_connection = True


def serve(cap, stop, ready):
    require(type(cap) is SyntheticCapability, 'SYNTHETIC_CAPABILITY_REQUIRED')
    p, r, _ = cap.recheck()
    f = p['fixture']
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            try:
                status, data = response(cap, self.path)
                scenarios = json.loads((Path(r['root']) / f['responses']).read_bytes())
                slot = urlsplit(self.path).path.removeprefix('/slot/')
                fault = scenarios['faults'].get(slot)
            except Exception:
                status, data, fault = 400, b'', None
            emit(self, status, data, fault=fault, stop=stop)

    # HTTPServer's default bind performs reverse DNS: explicitly avoid it.
    class NumericServer(HTTPServer):
        allow_reuse_address = False

        def server_bind(self):
            self.socket.bind(self.server_address)
            self.server_name, self.server_port = f['address'], f['port']

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(Path(r['root']) / f['certificate']),
                            str(Path(r['root']) / f['private_key']))
    server = NumericServer((f['address'], f['port']), Handler)
    try:
        server.socket = context.wrap_socket(server.socket, server_side=True)
        server.socket.settimeout(.5)
        server.timeout = .2
        ready()
        while not stop():
            server.handle_request()
    finally:
        server.server_close()
