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


from provider_gateway_https import Response, DeadlineReader, DeadlineSocket, bounded_https


class NativeHTTPS:
    def exchange(self, *, host, address, method, target, headers, body, tls_file, timeout, limit):
        """Production route admission remains independent of shared wire mechanics."""
        require(any(host == route[1] and method == route[0] and target.split('?', 1)[0] == route[2] for route in ROUTES.values()), 'NATIVE_ROUTE_REJECTED')
        address = str(ipaddress.IPv4Address(address))
        return bounded_https(host=host, address=address, port=443, method=method,
                             target=target, headers=headers, body=body,
                             tls_file=tls_file, timeout=timeout, limit=limit)


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
