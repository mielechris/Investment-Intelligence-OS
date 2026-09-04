from __future__ import annotations

import base64
import ctypes
import re
import subprocess
from dataclasses import dataclass
from typing import Protocol

SECURITY = "/usr/bin/security"
FRAMEWORK = "/System/Library/Frameworks/Security.framework/Security"
ERR_DUPLICATE_ITEM = -25299
ERR_ITEM_NOT_FOUND = -25300
_CANONICAL_32 = re.compile(rb"[A-Za-z0-9+/]{43}=")


@dataclass(frozen=True)
class CommandResult:
    returncode: int


class SecurityCommandRunner:
    """Metadata-only CLI runner. Secret stdin is deliberately prohibited."""

    def __init__(self, *, timeout: float = 5.0) -> None:
        if not 0 < timeout <= 10: raise ValueError("KEYCHAIN_TIMEOUT_INVALID")
        self.timeout = timeout

    def exists(self, *, service: str, account: str) -> bool:
        for value in (service, account):
            if not value or not value.isascii() or any(char.isspace() for char in value):
                raise ValueError("KEYCHAIN_SELECTOR_INVALID")
        argv = (SECURITY, "find-generic-password", "-s", service, "-a", account)
        try:
            completed = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env={"LC_ALL": "C", "LANG": "C"}, shell=False,
                timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired:
            raise RuntimeError("KEYCHAIN_COMMAND_TIMEOUT") from None
        if completed.returncode == 0: return True
        if completed.returncode == 44: return False
        raise RuntimeError("KEYCHAIN_COMMAND_FAILED")


def encode_key(key: bytes) -> bytes:
    if len(key) != 32: raise ValueError("KEY_SIZE_INVALID")
    return base64.b64encode(key)


def decode_key_output(output: bytes) -> bytes:
    if output.endswith(b"\r\n"): encoded = output[:-2]
    elif output.endswith(b"\n"): encoded = output[:-1]
    else: encoded = output
    if not _CANONICAL_32.fullmatch(encoded): raise RuntimeError("KEY_ENCODING_INVALID")
    try: decoded = base64.b64decode(encoded, validate=True)
    except Exception: raise RuntimeError("KEY_ENCODING_INVALID") from None
    if len(decoded) != 32 or base64.b64encode(decoded) != encoded:
        raise RuntimeError("KEY_ENCODING_INVALID")
    return decoded


class KeychainAPI(Protocol):
    def add(self, service: bytes, account: bytes, secret: bytes) -> int: ...
    def find(self, service: bytes, account: bytes) -> tuple[int, tuple[bytes, ...]]: ...
    def delete(self, service: bytes, account: bytes) -> int: ...


class SecurityFrameworkAPI:
    """Binary-safe wrapper over the macOS Security.framework generic-password API."""

    def __init__(self) -> None:
        try: self._security = ctypes.CDLL(FRAMEWORK)
        except OSError: raise RuntimeError("KEYCHAIN_FRAMEWORK_UNAVAILABLE") from None
        try: self._core = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        except OSError: raise RuntimeError("KEYCHAIN_FRAMEWORK_UNAVAILABLE") from None
        pointer, size = ctypes.c_void_p, ctypes.c_uint32
        self._security.SecKeychainAddGenericPassword.argtypes = [pointer, size, pointer, size, pointer, size, pointer,
            ctypes.POINTER(pointer)]
        self._security.SecKeychainAddGenericPassword.restype = ctypes.c_int32
        self._security.SecKeychainFindGenericPassword.argtypes = [pointer, size, pointer, size, pointer,
            ctypes.POINTER(size), ctypes.POINTER(pointer), ctypes.POINTER(pointer)]
        self._security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
        self._security.SecKeychainItemFreeContent.argtypes = [pointer, pointer]
        self._security.SecKeychainItemFreeContent.restype = ctypes.c_int32
        self._security.SecKeychainItemDelete.argtypes = [pointer]
        self._security.SecKeychainItemDelete.restype = ctypes.c_int32
        self._core.CFRelease.argtypes = [pointer]
        self._core.CFRelease.restype = None

    @staticmethod
    def _buffer(value: bytes):
        return ctypes.create_string_buffer(value, len(value))

    def add(self, service: bytes, account: bytes, secret: bytes) -> int:
        s, a, p = self._buffer(service), self._buffer(account), self._buffer(secret)
        return int(self._security.SecKeychainAddGenericPassword(None, len(service), s, len(account), a,
            len(secret), p, None))

    def find(self, service: bytes, account: bytes) -> tuple[int, tuple[bytes, ...]]:
        s, a = self._buffer(service), self._buffer(account)
        length, data = ctypes.c_uint32(), ctypes.c_void_p()
        status = int(self._security.SecKeychainFindGenericPassword(None, len(service), s, len(account), a,
            ctypes.byref(length), ctypes.byref(data), None))
        if status != 0: return status, ()
        try: secret = ctypes.string_at(data, length.value)
        finally: self._security.SecKeychainItemFreeContent(None, data)
        return 0, (secret,)

    def delete(self, service: bytes, account: bytes) -> int:
        s, a = self._buffer(service), self._buffer(account)
        item = ctypes.c_void_p()
        status = int(self._security.SecKeychainFindGenericPassword(None, len(service), s, len(account), a,
            None, None, ctypes.byref(item)))
        if status != 0: return status
        try: return int(self._security.SecKeychainItemDelete(item))
        finally: self._core.CFRelease(item)


class KeychainAdapter:
    def __init__(self, api: KeychainAPI, *, service: str) -> None:
        if not service or not service.isascii() or any(char.isspace() for char in service):
            raise ValueError("KEYCHAIN_SERVICE_INVALID")
        self.api, self.service = api, service.encode("ascii")

    @staticmethod
    def _account(key_id: str) -> bytes:
        if not key_id or not key_id.isascii() or any(char.isspace() for char in key_id):
            raise ValueError("KEY_ID_INVALID")
        return key_id.encode("ascii")

    def create(self, key_id: str, key: bytes) -> str:
        if len(key) != 32: raise ValueError("KEY_SIZE_INVALID")
        status = self.api.add(self.service, self._account(key_id), key)
        if status == ERR_DUPLICATE_ITEM: raise RuntimeError("KEY_RECORD_DUPLICATE")
        if status != 0: raise RuntimeError("KEYCHAIN_UNAVAILABLE")
        return "CREATED"

    def retrieve(self, key_id: str) -> bytes:
        status, matches = self.api.find(self.service, self._account(key_id))
        if status == ERR_ITEM_NOT_FOUND: raise RuntimeError("KEY_RECORD_MISSING")
        if status != 0: raise RuntimeError("KEYCHAIN_UNAVAILABLE")
        if len(matches) != 1 or len(matches[0]) != 32:
            raise RuntimeError("KEY_RECORD_INACCESSIBLE_OR_AMBIGUOUS")
        return matches[0]

    def delete(self, key_id: str, *, human_authorized: bool) -> str:
        if not human_authorized: raise PermissionError("KEY_DELETION_AUTHORIZATION_REQUIRED")
        status = self.api.delete(self.service, self._account(key_id))
        if status == ERR_ITEM_NOT_FOUND: return "ALREADY_ABSENT"
        if status != 0: raise RuntimeError("KEYCHAIN_UNAVAILABLE")
        return "DELETED"

    def rotate(self, old_id: str, new_id: str, new_key: bytes, *, recovery_verified: bool) -> str:
        if not recovery_verified: raise PermissionError("RECOVERY_VERIFICATION_REQUIRED")
        self.retrieve(old_id); self.create(new_id, new_key)
        return "ROTATION_STAGED"
