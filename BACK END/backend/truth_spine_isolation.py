"""Fail-closed process-wide no-spend boundary for the explicit isolated mode."""
import os
import sys


def enforce_offline() -> None:
    if not os.environ.get("IIOS_TRUTH_SPINE_CONFIG"):
        return

    def audit(event, args):
        if event == "socket.connect":
            address = args[1]
            if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1"}:
                raise PermissionError("ISOLATED_EXTERNAL_NETWORK_PROHIBITED")
        if event == "subprocess.Popen":
            executable = os.path.basename(str(args[0]))
            if executable != "ps":
                raise PermissionError("ISOLATED_SUBPROCESS_PROHIBITED")
        if event == "open" and isinstance(args[0], str):
            name = os.path.basename(args[0])
            if name == ".env" or "keychain" in args[0].lower() and not name.endswith((".py", ".pyc")):
                raise PermissionError("ISOLATED_CREDENTIAL_ACCESS_PROHIBITED")

    sys.addaudithook(audit)
