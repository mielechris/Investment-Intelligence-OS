"""Authenticated, fixed-path, coherent unattended-policy projection reader."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .unattended_tuesday import LKV_NAME, POLICY_NAME, STATE_NAME, PolicyStore, browser_projection, validate_policy, validate_session
from .unattended_tuesday_service import INSTALLATION_MANIFEST, OPERATIONAL_ROOT, _installed_commit

PROVENANCE_AUTHENTIC="AUTHENTIC_OPERATIONAL_POLICY_STATE"
PROVENANCE_ABSENT="POLICY_NOT_INSTALLED"
PROVENANCE_UNAVAILABLE="UNAVAILABLE"
PROVENANCE_SYNTHETIC="SYNTHETIC_FIXTURE_NON_LIVE"
MAX_BYTES=1_000_000
POLICY_FILES=frozenset({POLICY_NAME,STATE_NAME,LKV_NAME})

class UnattendedPolicyReader:
    def __init__(self,root:Path=OPERATIONAL_ROOT,manifest:Path=INSTALLATION_MANIFEST): self.root=root; self.manifest=manifest; self._identity="INITIAL"
    @property
    def cache_identity(self)->str:
        return self._filesystem_identity()

    @staticmethod
    def _bounded_regular_bytes(path:Path)->bytes:
        info=path.lstat()
        if (path.is_symlink() or not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.getuid()
                or not 0<info.st_size<=MAX_BYTES):
            raise ValueError("POLICY_FILE_INVALID")
        data=path.read_bytes()
        if len(data)!=info.st_size: raise ValueError("POLICY_FILE_CHANGED")
        return data

    def _filesystem_identity(self)->str:
        h=hashlib.sha256()
        for p in (self.manifest,self.root/POLICY_NAME,self.root/STATE_NAME,self.root/LKV_NAME):
            h.update(p.name.encode())
            try: h.update(self._bounded_regular_bytes(p))
            except FileNotFoundError: h.update(b"ABSENT")
            except (OSError,ValueError): h.update(b"UNAVAILABLE")
        return h.hexdigest()

    def _read_bytes(self)->tuple[bytes,bytes,bytes,bytes]:
        PolicyStore(self.root).validate_root()
        names={item.name for item in self.root.iterdir()}
        if not POLICY_FILES<=names or names-POLICY_FILES not in (set(),{"unattended-session.lock"}):
            raise ValueError("POLICY_INVENTORY_INVALID")
        result=[self._bounded_regular_bytes(self.manifest)]
        for name in (POLICY_NAME,STATE_NAME,LKV_NAME):
            result.append(self._bounded_regular_bytes(self.root/name))
        return tuple(result)  # type: ignore[return-value]

    def read(self)->dict[str,Any]|None:
        if not self.root.exists():
            value=browser_projection(None,None,read_at=datetime.now(timezone.utc).isoformat())
            value["provenance"]=PROVENANCE_ABSENT
            self._identity=self._filesystem_identity()
            return value
        for _ in range(3):
            try:
                first=self._read_bytes()
                installed=_installed_commit(self.manifest)
                policy=validate_policy(json.loads(first[1]),installed_commit=installed)
                state=validate_session(json.loads(first[2]),policy)
                lkv=validate_session(json.loads(first[3]),policy)
                if state!=lkv: raise ValueError("POLICY_STATE_AMBIGUOUS")
                if first!=self._read_bytes(): continue
                value=browser_projection(policy,state,read_at=datetime.now(timezone.utc).isoformat())
                value["provenance"]=PROVENANCE_AUTHENTIC
                self._identity=self._filesystem_identity()
                return value
            except FileNotFoundError:
                continue
            except (OSError,ValueError,json.JSONDecodeError):
                return None
        return None

def synthetic_absence_projection()->dict[str,Any]:
    value=browser_projection(None,None,read_at=datetime.now(timezone.utc).isoformat())
    value["provenance"]=PROVENANCE_SYNTHETIC
    return value
