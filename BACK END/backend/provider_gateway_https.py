"""Shared bounded wire mechanics. Callers must admit an exact destination first.

This module supplies no account, credential, dispatch or acceptance authority.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import http.client
import io
import socket
import ssl
import time


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


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


def bounded_https(*, host, address, port, method, target, headers, body,
                  tls_file, timeout, limit):
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
        sock.connect((address, port))
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
