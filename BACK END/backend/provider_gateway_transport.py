"""Single fixed-route HTTPS exchange; no retry, redirect, proxy or DNS fallback."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import http.client
import ipaddress
import io
from pathlib import Path
import json
import socket
import ssl
import time
from urllib.parse import urlencode

from provider_gateway_contract import safe_document
from provider_gateway_live_contract import Admission, ROUTES, require


@dataclass(repr=False)
class Response:
    status: int
    body: bytes = field(repr=False)
    request_start: str | None = None
    response_end: str | None = None

    def __repr__(self):
        return f'<Response status={self.status} body=redacted>'


class DeadlineReader(io.RawIOBase):
    def __init__(self, sock, remaining):
        super().__init__()
        self.sock, self.remaining = sock, remaining

    def readable(self):
        return True

    def readinto(self, buffer):
        self.sock.settimeout(self.remaining())
        count = self.sock.recv_into(buffer)
        self.remaining()
        return count


class DeadlineSocket:
    def __init__(self, sock, remaining):
        self.sock, self.remaining = sock, remaining

    def makefile(self, mode):
        require(mode == 'rb', 'RESPONSE_STREAM_MODE')
        return io.BufferedReader(DeadlineReader(self.sock, self.remaining))

    def sendall(self, data):
        self.sock.settimeout(self.remaining())
        self.sock.sendall(data)
        self.remaining()

    def close(self):
        # HTTPConnection may detach on Connection: close before reading the body.
        # NativeHTTPS owns the socket and closes it in its outer finally block.
        pass


class NativeHTTPS:
    def exchange(self, *, host, address, method, target, headers, body, tls_file, timeout, limit):
        """A pinned numeric address avoids unbounded resolver work or alternate IPs."""
        require(any(host == route[1] and method == route[0] and target.split('?', 1)[0] == route[2] for route in ROUTES.values()), 'NATIVE_ROUTE_REJECTED')
        address = str(ipaddress.IPv4Address(address))
        context = ssl.create_default_context(cafile=tls_file)
        require(context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname, 'TLS_REQUIRED')
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        deadline = time.monotonic() + timeout
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection = http.client.HTTPSConnection(host, timeout=timeout, context=context)
        def remaining():
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError('DEADLINE')
            return left
        try:
            sock.settimeout(remaining())
            sock.connect((address, 443))
            sock.settimeout(remaining())
            sock = context.wrap_socket(sock, server_hostname=host)
            connection.sock = DeadlineSocket(sock, remaining)
            sock.settimeout(remaining())
            request_start = datetime.now(timezone.utc).isoformat()
            connection.request(method, target, body=body, headers=headers)
            sock.settimeout(remaining())
            reply = connection.getresponse()
            # Headers and raw request targets are never returned to callers.
            remaining()
            if reply.status != 200:
                return Response(reply.status, b'', request_start, datetime.now(timezone.utc).isoformat())
            require(reply.getheader('Content-Encoding', 'identity') == 'identity', 'ENCODING_REJECTED')
            require('application/json' in reply.getheader('Content-Type', ''), 'CONTENT_TYPE_REJECTED')
            chunks, count = [], 0
            while True:
                sock.settimeout(remaining())
                chunk = reply.read1(min(65536, limit + 1 - count))
                remaining()
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
                require(count <= limit, 'BODY_TOO_LARGE')
            return Response(reply.status, b''.join(chunks), request_start, datetime.now(timezone.utc).isoformat())
        finally:
            connection.close()
            sock.close()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def exchange(admission, material, *, network, now):
    require(type(admission) is Admission, 'ADMISSION_REQUIRED')
    admission.recheck(now)
    m, _, r = admission.documents()
    from provider_gateway_qualification import verify_runtime
    verify_runtime(admission)
    require((m['mode'] == 'LIVE_QUALIFICATION') == (type(network) is NativeHTTPS), 'NETWORK_BOUNDARY_SCOPE')
    # Construct authentication inside this non-printing boundary only.
    headers = {'Accept': 'application/json', 'Accept-Encoding': 'identity'}
    parameters = dict(m['parameters'])
    values = material.values()
    target, body, reply, public = None, None, None, None
    failed = False
    status = None
    request_start = response_end = None
    try:
        p = m['provider']
        if p == 'ALPACA':
            headers.update({'APCA-API-KEY-ID': values[0].decode('ascii'), 'APCA-API-SECRET-KEY': values[1].decode('ascii')})
        elif p == 'MASSIVE':
            headers['Authorization'] = 'Bearer ' + values[0].decode('ascii')
        elif p == 'ALPHA_VANTAGE':
            parameters['apikey'] = values[0].decode('ascii')
        else:
            headers['X-API-KEY'] = values[0].decode('ascii')
        if m['method'] == 'POST':
            body = json.dumps(parameters, separators=(',', ':')).encode()
            headers['Content-Type'] = 'application/json'
            target = m['path']
        else:
            target = m['path'] + '?' + urlencode(parameters)
        require(len(target) <= 16000, 'URL_BOUND')
        reply = network.exchange(host=m['host'], address=r['network_addresses'][p], method=m['method'], target=target, headers=headers, body=body, tls_file=str(Path(r['root']) / r['tls']), timeout=m['timeout_seconds'], limit=m['maximum_response_bytes'])
        require(type(reply) is Response and type(reply.status) is int and type(reply.body) is bytes, 'RESPONSE_TYPE')
        status = reply.status
        request_start, response_end = reply.request_start, reply.response_end
        require(status == 200 and len(reply.body) <= m['maximum_response_bytes'], 'HTTP_OR_SIZE_REJECTED')
        material.reject_echo(reply.body)
        public = json.loads(reply.body, object_pairs_hook=_unique)
        # Detect unicode-escaped echoes after JSON decoding, before hashing.
        material.reject_echo(json.dumps(public, ensure_ascii=False).encode())
        safe_document(public)
        return {'status': status, 'body': reply.body, 'public': public, 'request_start': reply.request_start, 'response_end': reply.response_end}
    except Exception:
        failed = True
    finally:
        headers.clear()
        parameters.clear()
        values = ()
        target = body = reply = public = None
    if failed:
        # No underlying exception, URL, headers, provider message or body escapes.
        return {'status': status, 'body': None, 'public': None, 'failure': 'REQUEST_OR_RESPONSE_UNVERIFIED', 'request_start': request_start, 'response_end': response_end}
