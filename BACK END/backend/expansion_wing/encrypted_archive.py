from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

SCHEMA = "expansion-wing-encrypted-envelope-v1"


class KeyProvider(Protocol):
    def key(self, key_id: str) -> bytes: ...


class MacOSKeychainAdapter:
    """Inactive contract. Operational Keychain access requires a separately reviewed implementation."""
    status = "NOT_CONFIGURED"
    def key(self, _key_id: str) -> bytes:
        raise RuntimeError("KEY_RETRIEVAL_UNAVAILABLE")


@dataclass(frozen=True)
class EphemeralTestKeyProvider:
    keys: dict[str, bytes]
    def key(self, key_id: str) -> bytes:
        value = self.keys.get(key_id)
        if value is None or len(value) != 32: raise RuntimeError("KEY_RETRIEVAL_UNAVAILABLE")
        return value


class FixtureAuthenticatedCipher:
    """Fixture-only encrypt-then-MAC construction; prohibited for operational activation."""
    algorithm = "FIXTURE-HMAC-SHA256-ETM-V1"
    operationally_approved = False

    @staticmethod
    def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
        output = bytearray(); counter = 0
        while len(output) < length:
            output.extend(hmac.new(key, b"stream\0" + nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
            counter += 1
        return bytes(output[:length])

    def encrypt(self, key: bytes, plaintext: bytes, associated_data: bytes) -> tuple[bytes, bytes, bytes]:
        nonce = secrets.token_bytes(16); stream = self._stream(key, nonce, len(plaintext))
        ciphertext = bytes(left ^ right for left, right in zip(plaintext, stream))
        tag = hmac.new(key, b"tag\0" + associated_data + nonce + ciphertext, hashlib.sha256).digest()
        return nonce, ciphertext, tag

    def decrypt(self, key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes, associated_data: bytes) -> bytes:
        expected = hmac.new(key, b"tag\0" + associated_data + nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected): raise RuntimeError("ENVELOPE_AUTHENTICATION_FAILED")
        stream = self._stream(key, nonce, len(ciphertext))
        return bytes(left ^ right for left, right in zip(ciphertext, stream))


def _metadata(key_id: str, content_hash: str) -> dict[str, str]:
    return {"schema_version": SCHEMA, "algorithm": FixtureAuthenticatedCipher.algorithm,
            "key_id": key_id, "content_hash": content_hash}


def seal(plaintext: bytes, key_id: str, provider: KeyProvider, cipher: FixtureAuthenticatedCipher) -> bytes:
    key = provider.key(key_id); digest = hashlib.sha256(plaintext).hexdigest(); metadata = _metadata(key_id, digest)
    aad = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
    nonce, ciphertext, tag = cipher.encrypt(key, plaintext, aad)
    envelope = {**metadata, "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(), "tag": base64.b64encode(tag).decode()}
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def open_envelope(encoded: bytes, provider: KeyProvider, cipher: FixtureAuthenticatedCipher) -> bytes:
    try:
        envelope = json.loads(encoded); allowed = {"schema_version", "algorithm", "key_id", "content_hash",
            "nonce", "ciphertext", "tag"}
        if set(envelope) != allowed or envelope["schema_version"] != SCHEMA or envelope["algorithm"] != cipher.algorithm:
            raise RuntimeError("ENVELOPE_SCHEMA_INVALID")
        metadata = {key: envelope[key] for key in ("schema_version", "algorithm", "key_id", "content_hash")}
        aad = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
        plaintext = cipher.decrypt(provider.key(envelope["key_id"]), base64.b64decode(envelope["nonce"], validate=True),
            base64.b64decode(envelope["ciphertext"], validate=True), base64.b64decode(envelope["tag"], validate=True), aad)
        if hashlib.sha256(plaintext).hexdigest() != envelope["content_hash"]: raise RuntimeError("CONTENT_HASH_MISMATCH")
        return plaintext
    except RuntimeError: raise
    except Exception: raise RuntimeError("ENVELOPE_INVALID") from None


def atomic_write(path: Path, payload: bytes, *, before_replace: Callable[[], None] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700); path.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".encrypted-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        if before_replace: before_replace()
        os.replace(temporary, path); path.chmod(0o600)
    except Exception:
        try: os.close(descriptor)
        except OSError: pass
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise


def rotate(encoded: bytes, old_provider: KeyProvider, new_key_id: str, new_provider: KeyProvider,
           cipher: FixtureAuthenticatedCipher) -> bytes:
    plaintext = open_envelope(encoded, old_provider, cipher)
    return seal(plaintext, new_key_id, new_provider, cipher)
