"""Explicit protected inventory; no discovery of credentials or permanent ledgers."""
from pathlib import Path
import json
import os
import stat
import hashlib
from dataclasses import dataclass

from truth_spine_contract import canonical, seal
from truth_spine_lineage import OWNER_ROOT, SCOPE, check_pin, file_hash, hex_hash, require, safe_path, write_new

CATEGORIES = {'configurations','permanent_artifacts','retained_evidence','runtime_files','museum_assets'}


@dataclass(frozen=True)
class PinnedBaseline:
    raw: bytes
    expected_hash: str

    def decode(self):
        require(hex_hash(self.expected_hash) and hashlib.sha256(self.raw).hexdigest()==self.expected_hash,
                'BASELINE_SPEC_PIN_MISMATCH')
        return json.loads(self.raw)


def permitted(row):
    p=Path(row['path'])
    require(not p.is_relative_to(OWNER_ROOT), 'OWNER_SCOPE_SEPARATE')
    require(p.suffix.lower() not in {'.db','.sqlite','.sqlite3','.keychain','.keychain-db','.pem','.key'} and
            not p.name.endswith(('-wal','-shm','-journal')) and p.name != '.env' and
            not any(s.lower() in {'credentials','keychains','l7','l8'} for s in p.parts), 'PROHIBITED_BASELINE_PATH')
    return safe_path(p)


def load_baseline(path, expected):
    require(hex_hash(expected) and file_hash(path)==expected, 'BASELINE_SPEC_PIN_REQUIRED')
    pinned=PinnedBaseline(Path(path).read_bytes(),expected)
    return validate_baseline(pinned)


def validate_baseline(pinned):
    spec=pinned.decode()
    require(set(spec)=={'schema','files','trees','processes','listeners','owner_scope'} and
            spec['schema']=='iios-protected-baseline-v1' and spec['owner_scope']==SCOPE, 'BASELINE_SCHEMA')
    require(set(spec['files'])==CATEGORIES and len(spec['files']['configurations'])==37 and
            len(spec['files']['permanent_artifacts'])==5 and all(spec['files'].values()), 'COMPLETE_BASELINE_REQUIRED')
    require(spec['processes'] and spec['listeners'] and spec['trees'], 'COMPLETE_BASELINE_REQUIRED')
    paths=[]
    for rows in spec['files'].values():
        for row in rows:
            permitted(row);check_pin(row);paths.append(row['path'])
    require(len(paths)==len(set(paths)), 'DUPLICATE_BASELINE_ENTRY')
    members=[]
    for tree in spec['trees']:
        require(set(tree)=={'root','members'} and tree['members'] and len(tree['members'])==len(set(tree['members'])), 'TREE_INVENTORY_REQUIRED')
        root=safe_path(tree['root'])
        require(not root.is_relative_to(OWNER_ROOT) and root!=Path('/'), 'PROTECTED_TREE_SCOPE')
        for rel in tree['members']:
            from truth_spine_lineage import contained
            member=str(contained(root,rel))
            require(member in paths, 'UNPINNED_TREE_MEMBER')
            members.append(member)
    require(len(members)==len(set(members)) and set(members)==set(paths),'COMPLETE_EXACT_TREE_MEMBERSHIP_REQUIRED')
    for row in spec['processes']:
        require(set(row)=={'pid','parent_pid','start_time','executable','executable_hash','argv','cwd'} and
                type(row['pid']) is int and row['pid']>0 and hex_hash(row['executable_hash']), 'PROCESS_PIN_REQUIRED')
    require(len({r['pid'] for r in spec['processes']})==len(spec['processes']), 'DUPLICATE_PROCESS_PIN')
    require(all(set(r)=={'address','port','pid'} and r['address']=='127.0.0.1' and
                type(r['port']) is int and 0<r['port']<65536 and r['pid'] in {p['pid'] for p in spec['processes']}
                for r in spec['listeners']), 'LISTENER_OWNER_PIN_REQUIRED')
    require(len({(r['address'],r['port']) for r in spec['listeners']})==len(spec['listeners']),'DUPLICATE_LISTENER_PIN')
    return pinned


def observe(pinned, *, process_inventory, listener_inventory):
    require(isinstance(pinned,PinnedBaseline),'INDEPENDENT_BASELINE_REQUIRED')
    validate_baseline(pinned)
    spec=pinned.decode()
    rows=[]
    for category in sorted(spec['files']):
        for pin in spec['files'][category]:
            permitted(pin);check_pin(pin)
            s=Path(pin['path']).lstat()
            rows.append({'category':category,**pin,'uid':s.st_uid,'type':'regular'})
    trees=[]
    for tree in spec['trees']:
        root=safe_path(tree['root']);actual=[]
        for base,dirs,files in os.walk(root,followlinks=False):
            for name in dirs+files:
                p=Path(base)/name
                require(not p.is_symlink(), 'BASELINE_SYMLINK')
                if not p.is_dir():
                    require(stat.S_ISREG(p.lstat().st_mode), 'BASELINE_SPECIAL_FILE')
                    actual.append(p.relative_to(root).as_posix())
        require(sorted(actual)==sorted(tree['members']), 'BASELINE_TREE_CHANGED')
        trees.append({'root':str(root),'members':sorted(actual)})
    processes=process_inventory(spec['processes'])
    listeners=listener_inventory(spec['listeners'])
    require(processes==spec['processes'] and listeners==spec['listeners'], 'PROTECTED_PROCESS_OR_LISTENER_CHANGED')
    return seal({'schema':'iios-noninterference-observation-v1','files':rows,'trees':trees,
                 'processes':processes,'listeners':listeners,'owner_scope':SCOPE})


def finish(root, before, after):
    require(before==after,'NONINTERFERENCE_FAILED')
    return write_new(root,'baselines/after.json',canonical(after))
