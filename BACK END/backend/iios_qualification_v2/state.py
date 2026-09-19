"""Append-only checkpoints are authoritative; state.json is a rebuildable projection."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid

AUTHORITY = dict(broker_connection=False, paper_order_permission=False,
                 trade_execution=False, live_execution=False)
STAGES = ('source_lock', 'runtime', 'boot', 'ownership', 'confinement',
          'startup_ack', 'loopback_tls', 'truth_spine', 'cleanup', 'export')


def require(value, code):
    if not value:
        raise ValueError(code)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: require(False, 'NONFINITE_JSON'))


def directory(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'ROOT_PATH')
    for parent in reversed((path, *path.parents)):
        if parent.exists() or parent.is_symlink():
            st = parent.lstat()
            require(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode), 'ROOT_ALIAS')
            require(st.st_uid in (0, os.getuid()) and not st.st_mode & 0o022, 'ROOT_OWNER')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = path.stat()
    require(st.st_uid == os.getuid() and stat.S_IMODE(st.st_mode) == 0o700, 'ROOT_MODE')
    return path


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish(path, value):
    path = Path(path)
    raw = canonical(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    fsync_dir(path.parent)
    return file_hash(path)


class Store:
    def __init__(self, root):
        self.root = directory(root)
        self.events = directory(self.root/'checkpoints')

    @contextlib.contextmanager
    def locked(self):
        fd = os.open(self.root/'controller.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            require(os.fstat(fd).st_uid == os.getuid() and os.fstat(fd).st_nlink==1 and stat.S_IMODE(os.fstat(fd).st_mode)==0o600, 'LOCK_OWNER')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    def load(self):
        previous = None
        records = []
        for index, path in enumerate(sorted(self.events.iterdir())):
            require(path.name == f'{index:08d}.json' and not path.is_symlink(), 'CHECKPOINT_SEQUENCE')
            st = path.stat()
            require(st.st_uid == os.getuid() and stat.S_IMODE(st.st_mode) == 0o400 and st.st_nlink == 1, 'CHECKPOINT_MODE')
            row = decode(path.read_bytes())
            require(set(row) == {'schema','sequence','previous','event','data','authority','hash'}, 'CHECKPOINT_SCHEMA')
            require(row['schema'] == 2 and row['sequence'] == index and row['previous'] == previous, 'CHECKPOINT_PARENT')
            require(row['authority'] == AUTHORITY and all(v is False for v in row['authority'].values()), 'AUTHORITY')
            body = {k:v for k,v in row.items() if k != 'hash'}
            require(digest(body) == row['hash'], 'CHECKPOINT_HASH')
            records.append(row); previous = row['hash']
        return records

    def append(self, event, data):
        records = self.load()
        row = dict(schema=2, sequence=len(records), previous=records[-1]['hash'] if records else None,
                   event=event, data=data, authority=AUTHORITY)
        row['hash'] = digest(row)
        publish(self.events/f'{len(records):08d}.json', row)
        # Atomic convenience projection; never trusted in place of the journal.
        temp = self.root/('state-'+uuid.uuid4().hex+'.next')
        publish(temp, dict(schema=2, head=row['hash'], sequence=row['sequence'], event=event, data=data, authority=AUTHORITY))
        os.replace(temp, self.root/'state.json'); fsync_dir(self.root)
        return row

    def begin(self, source, boot, *, resume):
        records = self.load()
        if records:
            require(resume, 'EXPLICIT_RESUME_REQUIRED')
        # Every explicit invocation revalidates native prerequisites. Old receipts stay immutable.
        data = dict(source=source, boot=boot, revision=sum(r['event']=='BEGIN' for r in records),
                    invalidates=list(STAGES), reason='EXPLICIT_RESUME' if records else 'INITIAL')
        return self.append('BEGIN', data)['data']


def historical_exception(historical, current_boot):
    require(historical['cleanup'] == 'NOT_ESTABLISHED', 'HISTORICAL_CLEANUP')
    require(historical['boot'] != current_boot, 'SAME_BOOT_UNRESOLVED')
    return dict(historical=historical, current_boot=current_boot,
                disposition='PRIOR_BOOT_PROCESS_CANNOT_SURVIVE_CURRENT_BOOT', cleanup_upgraded=False)


def verify_export(root):
    root = Path(root)
    mp=root/'manifest.json'
    require(not mp.is_symlink() and mp.is_file() and mp.stat().st_nlink==1 and mp.stat().st_uid==os.getuid() and stat.S_IMODE(mp.stat().st_mode)==0o400,'EXPORT_MANIFEST')
    manifest = decode(mp.read_bytes())
    require(manifest.get('schema')==2 and set(manifest.get('files',{}))=={'summary.json','journal.json'},'EXPORT_SCHEMA')
    require(not root.is_symlink() and stat.S_IMODE(root.stat().st_mode)==0o500, 'EXPORT_MODE')
    expected = {'manifest.json'} | set(manifest['files'])
    require({p.name for p in root.iterdir()} == expected, 'EXPORT_MEMBERSHIP')
    for name, expected_hash in manifest['files'].items():
        p = root/name
        require(p.name == name and not p.is_symlink() and p.is_file() and p.stat().st_nlink == 1,
                'EXPORT_PATH')
        require(stat.S_IMODE(p.stat().st_mode)==0o400 and file_hash(p)==expected_hash, 'EXPORT_HASH')
    return manifest


def export(store, evidence, summary):
    evidence = directory(evidence)
    records = store.load()
    destination = evidence/records[-1]['hash']
    destination.mkdir(mode=0o700)  # Never replace an earlier export.
    files = {'summary.json': publish(destination/'summary.json', summary),
             'journal.json': publish(destination/'journal.json', records)}
    publish(destination/'manifest.json', dict(schema=2, journal_head=records[-1]['hash'], files=files))
    destination.chmod(0o500); fsync_dir(evidence)
    verify_export(destination)
    return str(destination)
