"""TEST ONLY. Explicit offline boundary scopes; never shipped as runtime authority.

Decorated tests exercise synthetic credentials/transports, not real capabilities.
Production require_capability is unchanged and restored after each invocation.
An irreversible audit hook denies real provider/Keychain and permanent writes.
"""
from __future__ import annotations

import contextvars
import functools
import os
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

_scope = contextvars.ContextVar('isolated_test_authority', default=None)
_active = set()
_audit_installed = False


@dataclass(frozen=True)
class OfflineTestAuthority:
    test_identity: str
    capabilities: frozenset[str]
    classification: str = 'SYNTHETIC_OFFLINE_TEST_ONLY'


def _install_audit():
    global _audit_installed
    if _audit_installed: return
    temp_roots = (Path('/private/tmp'), Path(tempfile.gettempdir()).resolve())
    def audit(event, args):
        if event in {'socket.connect', 'socket.bind'}:
            address=args[1]
            if (not isinstance(address,tuple) or address[0] not in {'127.0.0.1','::1','localhost'}
                    or address[1] in {5176,5177,5184,5185,5186,8002}):
                raise PermissionError('OFFLINE_TEST_NETWORK_DENIED')
        if event == 'ctypes.dlopen' and args[0] and 'Security.framework' in str(args[0]):
            raise PermissionError('OFFLINE_TEST_KEYCHAIN_DENIED')
        if event == 'subprocess.Popen' and Path(str(args[0])).name in {'security','curl','osascript','launchctl'}:
            raise PermissionError('OFFLINE_TEST_OPERATIONAL_COMMAND_DENIED')
        if event == 'open' and isinstance(args[0], str):
            p=Path(args[0])
            if p.name == '.env' or 'Keychains' in p.parts or p.suffix in {'.keychain','.keychain-db'}:
                raise PermissionError('OFFLINE_TEST_CREDENTIAL_FILE_DENIED')
            flags=args[2]
            if isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC):
                absolute=p.resolve()
                if absolute != Path('/dev/null') and not any(absolute.is_relative_to(t) for t in temp_roots):
                    raise PermissionError('OFFLINE_TEST_PERMANENT_WRITE_DENIED')
    sys.addaudithook(audit)
    _audit_installed=True


def offline_boundary(*capabilities: str):
    """Per-test declaration permitting ONLY the named mocked boundary algorithms."""
    granted=frozenset(capabilities)
    if not granted or not granted <= {'provider_requests','credential_access'}:
        raise ValueError('TEST_CAPABILITY_NOT_ALLOWED')
    def decorate(function):
        if not function.__name__.startswith('test_') or not function.__module__.split('.')[-1].startswith('test_'):
            raise ValueError('TEST_FUNCTION_REQUIRED')
        @functools.wraps(function)
        def wrapped(*args,**kwargs):
            from truth_spine_authority import require_capability
            _install_audit()
            authority=OfflineTestAuthority(function.__module__+'.'+function.__qualname__,granted)
            token=object(); _active.add(token); scope_token=_scope.set((token,authority))
            def test_guard(capability, **context):
                current=_scope.get()
                if (current is None or current[0] not in _active or current[1] != authority
                        or capability not in authority.capabilities or context.get('document') is not None):
                    return require_capability(capability,**context)
                return None
            original_thread=threading.Thread
            class ScopedTestThread(original_thread):
                def __init__(self,*a,**kw):
                    kw.setdefault('context',contextvars.copy_context())
                    super().__init__(*a,**kw)
            try:
                with patch('truth_spine_authority.require_capability',test_guard), patch('threading.Thread',ScopedTestThread):
                    return function(*args,**kwargs)
            finally:
                _active.remove(token); _scope.reset(scope_token)
        return wrapped
    return decorate
