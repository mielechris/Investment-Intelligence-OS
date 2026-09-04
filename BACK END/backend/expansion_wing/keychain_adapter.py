from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes = b""


class CommandRunner(Protocol):
    def run(self, argv: tuple[str, ...], *, stdin: bytes | None, environment: dict[str, str]) -> CommandResult: ...


class KeychainAdapter:
    def __init__(self, runner: CommandRunner, *, service: str) -> None:
        if not service or any(char.isspace() for char in service): raise ValueError("KEYCHAIN_SERVICE_INVALID")
        self.runner = runner; self.service = service

    def _run(self, action: str, key_id: str, secret: bytes | None = None) -> CommandResult:
        if not key_id or any(char.isspace() for char in key_id): raise ValueError("KEY_ID_INVALID")
        commands = {
            "create": ("/usr/bin/security", "add-generic-password", "-a", key_id, "-s", self.service, "-w"),
            "retrieve": ("/usr/bin/security", "find-generic-password", "-a", key_id, "-s", self.service, "-w"),
            "delete": ("/usr/bin/security", "delete-generic-password", "-a", key_id, "-s", self.service),
        }
        return self.runner.run(commands[action], stdin=secret, environment={})

    def create(self, key_id: str, key: bytes) -> str:
        if len(key) != 32: raise ValueError("KEY_SIZE_INVALID")
        result = self._run("create", key_id, key)
        if result.returncode == 45: raise RuntimeError("KEY_RECORD_DUPLICATE")
        if result.returncode != 0: raise RuntimeError("KEYCHAIN_UNAVAILABLE")
        return "CREATED"

    def retrieve(self, key_id: str) -> bytes:
        result = self._run("retrieve", key_id)
        if result.returncode == 44: raise RuntimeError("KEY_RECORD_MISSING")
        if result.returncode != 0 or len(result.stdout.rstrip(b"\n")) != 32: raise RuntimeError("KEY_RECORD_INACCESSIBLE_OR_AMBIGUOUS")
        return result.stdout.rstrip(b"\n")

    def delete(self, key_id: str, *, human_authorized: bool) -> str:
        if not human_authorized: raise PermissionError("KEY_DELETION_AUTHORIZATION_REQUIRED")
        if self._run("delete", key_id).returncode != 0: raise RuntimeError("KEYCHAIN_UNAVAILABLE")
        return "DELETED"

    def rotate(self, old_id: str, new_id: str, new_key: bytes, *, recovery_verified: bool) -> str:
        if not recovery_verified: raise PermissionError("RECOVERY_VERIFICATION_REQUIRED")
        self.retrieve(old_id); self.create(new_id, new_key); return "ROTATION_STAGED"
