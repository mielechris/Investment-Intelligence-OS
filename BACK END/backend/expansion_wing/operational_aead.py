from __future__ import annotations

import base64
import importlib.util
import json
import secrets
from dataclasses import dataclass, field
from typing import Protocol

ALGORITHM = "AES-256-GCM"
SCHEMA = "expansion-wing-operational-aead-v1"
MAX_PLAINTEXT = 25_000_000


class AEADBackend(Protocol):
    def encrypt(self, key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes: ...
    def decrypt(self, key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes: ...


class CryptographyAESGCMBackend:
    def __init__(self) -> None:
        if importlib.util.find_spec("cryptography") is None: raise RuntimeError("OPERATIONAL_AEAD_NOT_AVAILABLE")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        self._type = AESGCM
    def encrypt(self, key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
        return self._type(key).encrypt(nonce, plaintext, aad)
    def decrypt(self, key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
        try: return self._type(key).decrypt(nonce, ciphertext, aad)
        except Exception: raise RuntimeError("AEAD_AUTHENTICATION_FAILED") from None


def dependency_status() -> str:
    return "AVAILABLE_FOR_REVIEW" if importlib.util.find_spec("cryptography") is not None else "NOT_AVAILABLE"


@dataclass
class OperationalAEAD:
    backend: AEADBackend
    used_nonces: set[bytes] = field(default_factory=set)

    def seal(self, plaintext: bytes, key: bytes, *, key_id: str, metadata: dict[str, str], nonce: bytes | None = None) -> bytes:
        if len(key) != 32: raise ValueError("AES_256_KEY_REQUIRED")
        if not plaintext or len(plaintext) > MAX_PLAINTEXT: raise ValueError("PLAINTEXT_SIZE_INVALID")
        if not key_id or set(metadata) - {"record_type", "created_at", "content_hash"}:
            raise ValueError("AUTHENTICATED_METADATA_INVALID")
        selected = secrets.token_bytes(12) if nonce is None else nonce
        if len(selected) != 12 or selected in self.used_nonces: raise RuntimeError("NONCE_REUSE_REJECTED")
        header = {"schema_version": SCHEMA, "algorithm": ALGORITHM, "key_id": key_id, "metadata": metadata}
        aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
        ciphertext = self.backend.encrypt(key, selected, plaintext, aad); self.used_nonces.add(selected)
        if len(ciphertext) > MAX_PLAINTEXT + 32: raise RuntimeError("CIPHERTEXT_SIZE_INVALID")
        return json.dumps({**header, "nonce": base64.b64encode(selected).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode()}, sort_keys=True, separators=(",", ":")).encode()

    def open(self, encoded: bytes, key: bytes) -> bytes:
        if len(encoded) > MAX_PLAINTEXT * 2: raise ValueError("ENVELOPE_SIZE_INVALID")
        try: value = json.loads(encoded)
        except Exception: raise RuntimeError("AEAD_ENVELOPE_INVALID") from None
        if set(value) != {"schema_version", "algorithm", "key_id", "metadata", "nonce", "ciphertext"}:
            raise RuntimeError("AEAD_ENVELOPE_INVALID")
        if value["schema_version"] != SCHEMA or value["algorithm"] != ALGORITHM:
            raise RuntimeError("AEAD_DOWNGRADE_REJECTED")
        if len(key) != 32 or not isinstance(value["metadata"], dict): raise RuntimeError("AEAD_ENVELOPE_INVALID")
        header = {key_name: value[key_name] for key_name in ("schema_version", "algorithm", "key_id", "metadata")}
        aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
        try:
            nonce = base64.b64decode(value["nonce"], validate=True); ciphertext = base64.b64decode(value["ciphertext"], validate=True)
        except Exception: raise RuntimeError("AEAD_ENVELOPE_INVALID") from None
        if len(nonce) != 12 or len(ciphertext) > MAX_PLAINTEXT + 32: raise RuntimeError("AEAD_ENVELOPE_INVALID")
        return self.backend.decrypt(key, nonce, ciphertext, aad)


def reject_fixture_cipher_for_operations(cipher: object) -> None:
    if not getattr(cipher, "operationally_approved", False): raise RuntimeError("FIXTURE_CIPHER_OPERATIONAL_REJECTION")


AES256_GCM_KAT = {"key": bytes(32), "nonce": bytes(12), "plaintext": bytes(16), "aad": b"",
    "ciphertext_and_tag": bytes.fromhex("cea7403d4d606b6e074ec5d3baf39d18d0d1c8a799996bf0265b98b5d48ab919")}


def known_answer_check(backend: AEADBackend) -> bool:
    vector = AES256_GCM_KAT
    encrypted = backend.encrypt(vector["key"], vector["nonce"], vector["plaintext"], vector["aad"])
    return encrypted == vector["ciphertext_and_tag"] and backend.decrypt(
        vector["key"], vector["nonce"], encrypted, vector["aad"]) == vector["plaintext"]
