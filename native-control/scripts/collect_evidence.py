#!/usr/bin/env python3
"""Verify one sanitized v2 export and copy only its sealed public projection."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

AUTHORITY={'broker_connection':False,'paper_order_permission':False,
           'trade_execution':False,'live_execution':False}

def require(value,code):
    if not value:raise ValueError(code)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def scan(value):
    forbidden_keys={'hardware_uuid','runner_name','run_id','run_attempt','device','inode','uid'}
    patterns=(r'/Users/[^/\s]+',r'gh[pousr]_[A-Za-z0-9]{20,}',r'github_pat_[A-Za-z0-9_]{20,}',
              r'AKIA[A-Z0-9]{16}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
              r'authorization:',r'bearer\s+',r'password=',r'token=')
    if isinstance(value,dict):
        require(not forbidden_keys.intersection(value),'MACHINE_IDENTITY')
        require(not any(any(re.search(p,key,re.I) for p in patterns) for key in value),'SECRET_KEY')
        [scan(v) for v in value.values()]
    elif isinstance(value,list):[scan(v) for v in value]
    elif isinstance(value,str):require(not any(re.search(p,value,re.I) for p in patterns),'SECRET_OR_MACHINE_PATH')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--result',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();result=json.loads(Path(args.result).read_bytes())
    require(result['status'] in ('GREEN','RED') and result.get('export'),'NATIVE_RESULT')
    root=Path.home()/'Library/IIOS/evidence';source=Path(result['export'])
    require(source.parent==root and source.is_dir() and not source.is_symlink(),'EXPORT_PATH')
    manifest=json.loads((source/'manifest.json').read_bytes());require(manifest['schema']==2,'EXPORT_SCHEMA')
    require(set(manifest['files'])=={'summary.json','journal.json'},'EXPORT_MEMBERSHIP')
    require({p.name for p in source.iterdir()}=={'manifest.json','summary.json','journal.json'},'EXPORT_EXTRA_FILE')
    for name,value in manifest['files'].items():require(sha(source/name)==value,'EXPORT_HASH')
    summary=json.loads((source/'summary.json').read_bytes());journal=json.loads((source/'journal.json').read_bytes())
    scan(manifest);scan(summary);scan(journal)
    require(summary['authority']==AUTHORITY and summary['provider_requests']==0 and
            summary['historical_cleanup']=='NOT_ESTABLISHED','EXPORT_AUTHORITY')
    output=Path(args.output);output.mkdir(mode=0o700)
    for name in ('manifest.json','summary.json','journal.json'):
        with (output/name).open('xb') as target,(source/name).open('rb') as original:shutil.copyfileobj(original,target)
        (output/name).chmod(0o400)
    hashes={name:sha(output/name) for name in ('manifest.json','summary.json','journal.json')}
    (output/'artifact-hashes.json').write_text(json.dumps(hashes,sort_keys=True,separators=(',',':'))+'\n');(output/'artifact-hashes.json').chmod(0o400)
    output.chmod(0o500);print(str(output))

if __name__=='__main__':main()
