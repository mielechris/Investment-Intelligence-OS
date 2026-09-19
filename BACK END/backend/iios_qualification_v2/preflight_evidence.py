"""Sealed failure receipts for admission that stops before the v2 journal exists."""
import datetime
import errno
import os
from pathlib import Path
import re
import stat
import time
import uuid

from .roots import contained
from .state import AUTHORITY, canonical, decode, file_hash, fsync_dir, publish, require, sanitized


class EvidenceUnavailable(RuntimeError):
    pass


def _category(error):
    value=str(error)
    if re.fullmatch(r'[A-Z0-9_:-]{1,160}',value):return value
    return type(error).__name__.upper()


def _errno(error):
    value=getattr(error,'errno',None)
    return errno.errorcode.get(value,'NONE') if isinstance(value,int) else 'NONE'


class Writer:
    """Creates one exclusive, owner-only receipt directory per rejected admission."""
    def __init__(self, evidence, bound, *, started=None):
        self.bound=bound;self.started=time.monotonic() if started is None else started
        try:
            self.root=contained(Path(evidence)/'preflight',bound)
            st=self.root.lstat()
            require(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode) and st.st_uid==os.getuid() and
                    stat.S_IMODE(st.st_mode)==0o700,'PREFLIGHT_EVIDENCE_ROOT')
        except BaseException as error:
            raise EvidenceUnavailable('EVIDENCE_EXPORT_UNAVAILABLE') from error

    def write(self, *, error, stage, parents, expected, observed):
        try:
            name='receipt-'+uuid.uuid4().hex
            destination=self.root/name
            os.mkdir(destination,0o700)
            st=destination.lstat()
            require(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode) and st.st_uid==os.getuid() and
                    stat.S_IMODE(st.st_mode)==0o700,'PREFLIGHT_RECEIPT_ROOT')
            core=dict(schema='iios-native-preflight-evidence-v1',status='RED',stage=stage,
                      predicate=_category(error),exception_category=type(error).__name__,errno_category=_errno(error),
                      parents=sanitized(parents),expected=sanitized(expected),observed=sanitized(observed),
                      authority=AUTHORITY,provider_requests=0,
                      timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      monotonic_elapsed_ms=int((time.monotonic()-self.started)*1000))
            core_hash=publish(destination/'receipt-core.json',core)
            manifest=dict(schema=1,files={'receipt-core.json':core_hash},authority=AUTHORITY,provider_requests=0)
            manifest_hash=publish(destination/'manifest.json',manifest)
            receipt=dict(schema='iios-native-preflight-receipt-v1',status='RED',stage=stage,
                         predicate=_category(error),exception_category=type(error).__name__,errno_category=_errno(error),
                         parents=sanitized(parents),expected=sanitized(expected),observed=sanitized(observed),
                         authority=AUTHORITY,provider_requests=0,
                         timestamp_utc=core['timestamp_utc'],monotonic_elapsed_ms=core['monotonic_elapsed_ms'],
                         receipt_core_sha256=core_hash,evidence_manifest_sha256=manifest_hash)
            receipt_hash=publish(destination/'receipt.json',receipt)
            require(file_hash(destination/'receipt-core.json')==core_hash and file_hash(destination/'manifest.json')==manifest_hash and
                    file_hash(destination/'receipt.json')==receipt_hash,'PREFLIGHT_RECEIPT_HASH')
            for item in (destination/'receipt-core.json',destination/'manifest.json',destination/'receipt.json'):
                st=item.lstat();require(stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode) and st.st_uid==os.getuid() and
                                           stat.S_IMODE(st.st_mode)==0o400,'PREFLIGHT_RECEIPT_FILE')
            destination.chmod(0o500);fsync_dir(self.root)
            return dict(export=str(destination),manifest_sha256=manifest_hash,receipt_sha256=receipt_hash)
        except BaseException as failure:
            raise EvidenceUnavailable('EVIDENCE_EXPORT_UNAVAILABLE') from failure


def parents_from_host(path):
    """Extract only declared parent categories; malformed host content never becomes evidence text."""
    result=dict(source=dict(category='UNAVAILABLE'),app=dict(category='UNAVAILABLE'),manifest=dict(category='UNAVAILABLE'))
    try:
        host=decode(Path(path).read_bytes())
        for key in ('repository','commit','branch','inventory_sha256'):
            if isinstance(host.get(key),str):result['source'][key]=host[key]
        for key in ('app_identifier','app_executable_sha256'):
            if isinstance(host.get(key),str):result['app'][key]=host[key]
        for key in ('app_manifest_sha256',):
            if isinstance(host.get(key),str):result['manifest'][key]=host[key]
    except BaseException:
        pass
    return result
