"""No import-time Keychain access. Values never have a printable representation."""
from __future__ import annotations

from contextlib import contextmanager
from urllib.parse import quote
import base64
import json

from provider_gateway_live_contract import Admission, SELECTORS, require


class SecretMaterial:
    __slots__ = ('_values',)

    def __init__(self, values):
        self._values = [bytearray(v) for v in values]

    def __repr__(self):
        return '<SecretMaterial redacted>'

    def values(self):
        require(bool(self._values), 'SECRET_CLOSED')
        return tuple(bytes(v) for v in self._values)

    def reject_echo(self, body):
        """Inspect before any body hash; includes common JSON/URL/base64 encodings."""
        for value in self.values():
            variants = (value, quote(value.decode('ascii'), safe='').encode(), base64.b64encode(value), json.dumps(value.decode('ascii'))[1:-1].encode())
            require(not any(v in body for v in variants), 'SENSITIVE_RESPONSE')

    def close(self):
        for value in self._values:
            value[:] = b'\0' * len(value)
        self._values.clear()


class MacKeychain:
    """Read exact generic-password item via Security.framework, only when called."""
    def read(self, service, account):
        # No CLI password output, argv/env secret transport, enumeration or writes.
        import ctypes
        from ctypes import c_void_p, c_uint32, c_int32, POINTER, byref
        api = ctypes.CDLL('/System/Library/Frameworks/Security.framework/Security')
        api.SecKeychainFindGenericPassword.argtypes = [c_void_p, c_uint32, c_void_p, c_uint32, c_void_p, POINTER(c_uint32), POINTER(c_void_p), c_void_p]
        api.SecKeychainFindGenericPassword.restype = c_int32
        api.SecKeychainItemFreeContent.argtypes = [c_void_p, c_void_p]
        api.SecKeychainItemFreeContent.restype = c_int32
        s, a = service.encode('ascii'), account.encode('ascii')
        length, data = c_uint32(), c_void_p()
        status = api.SecKeychainFindGenericPassword(None, len(s), s, len(a), a, byref(length), byref(data), None)
        require(status == 0, 'CREDENTIAL_UNAVAILABLE')
        try:
            require(8 <= length.value <= 1024, 'CREDENTIAL_INVALID')
            return ctypes.string_at(data, length.value)
        finally:
            api.SecKeychainItemFreeContent(None, data)


@contextmanager
def credential_scope(admission, *, backend, now):
    require(type(admission) is Admission, 'ADMISSION_REQUIRED')
    admission.recheck(now)
    m, _, _ = admission.documents()
    from provider_gateway_qualification import verify_runtime
    verify_runtime(admission)
    require((m['mode'] == 'LIVE_QUALIFICATION') == (type(backend) is MacKeychain), 'CREDENTIAL_BOUNDARY_SCOPE')
    values = []
    material = None
    failed = False
    try:
        for service in SELECTORS[m['provider']]:
            value = backend.read(service, 'iios-provider')
            require(type(value) is bytes and 8 <= len(value) <= 1024 and all(33 <= c <= 126 for c in value), 'CREDENTIAL_INVALID')
            values.append(value)
        material = SecretMaterial(values)
    except Exception:
        failed = True
    finally:
        values.clear()
    if failed:
        raise ValueError('CREDENTIAL_UNAVAILABLE') from None
    try:
        yield material
    finally:
        material.close()
