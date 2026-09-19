#!/usr/bin/env python3
"""Standalone verifier: it must run before any checked-out IIOS code."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess

AUTHORITY={'broker_connection':False,'paper_order_permission':False,
           'trade_execution':False,'live_execution':False}
ENV={'PATH':'/usr/bin:/bin:/usr/sbin','LC_ALL':'C','TZ':'UTC',
     'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}

def require(value, code):
    if not value:raise ValueError(code)

def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()

def digest(value):return hashlib.sha256(canonical(value)).hexdigest()

def decode(path):
    def unique(pairs):
        value={}
        for key,item in pairs:
            require(key not in value,'DUPLICATE_JSON_KEY');value[key]=item
        return value
    return json.loads(Path(path).read_bytes(),object_pairs_hook=unique,
                      parse_constant=lambda _:require(False,'NONFINITE_JSON'))

def command(args,root):
    result=subprocess.run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',*args],
                          cwd=root,env=ENV,stdin=subprocess.DEVNULL,capture_output=True,timeout=30,close_fds=True)
    require(len(result.stdout)+len(result.stderr)<=8*1024*1024,'GIT_OUTPUT_BOUND')
    require(result.returncode==0,'GIT_COMMAND');return result

def inventory(root):
    raw=command(['ls-files','--stage','-z'],root).stdout;rows=[]
    for record in raw.split(b'\0'):
        if not record:continue
        header,name=record.split(b'\t',1);mode,blob,stage=header.decode('ascii').split(' ')
        path=name.decode('utf-8');pure=PurePosixPath(path)
        require(stage=='0' and mode in ('100644','100755'),'SOURCE_INDEX_MODE')
        require(not pure.is_absolute() and '..' not in pure.parts and
                not any(ord(c)<32 for c in path),'SOURCE_PATH')
        item=(root/pure);st=item.lstat()
        require(stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode),'SOURCE_FILE_TYPE')
        data=item.read_bytes();actual_mode=stat.S_IMODE(st.st_mode)
        require(actual_mode==(0o755 if mode=='100755' else 0o644),'SOURCE_WORKTREE_MODE')
        rows.append({'path':path,'bytes':len(data),'mode':actual_mode,
                     'sha256':hashlib.sha256(data).hexdigest()})
    require(rows and rows==sorted(rows,key=lambda row:row['path']),'SOURCE_INVENTORY_ORDER')
    actual=[]
    for item in root.rglob('*'):
        relative=item.relative_to(root)
        if '.git' in relative.parts:continue
        st=item.lstat();require(not stat.S_ISLNK(st.st_mode) and
                               (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)),
                               'SOURCE_EXTRA_TYPE')
        if stat.S_ISREG(st.st_mode):actual.append(relative.as_posix())
    tracked=[row['path'] for row in rows]
    require(len({name.casefold() for name in tracked})==len(tracked) and
            len(actual)==len(tracked) and
            {name.casefold() for name in actual}=={name.casefold() for name in tracked},
            'SOURCE_EXTRA_FILE')
    return rows

def verify(binding_path,source,receipt):
    binding=decode(binding_path);source=Path(source).resolve(strict=True)
    require(set(binding)=={'schema','repository','commit','inventory','inventory_sha256','authority'},'BINDING_SCHEMA')
    require(binding['schema']==1 and binding['authority']==AUTHORITY,'BINDING_AUTHORITY')
    require(binding['repository']=='mielechris/Investment-Intelligence-OS','SOURCE_REPOSITORY')
    require(re.fullmatch(r'[0-9a-f]{40}',binding['commit']) and
            re.fullmatch(r'[0-9a-f]{64}',binding['inventory_sha256']),'BINDING_DIGEST')
    require(os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch' and
            os.environ.get('GITHUB_REPOSITORY')=='mielechris/IIOS-Native-Control' and
            os.environ.get('GITHUB_REF')=='refs/heads/main' and
            os.environ.get('GITHUB_REF_TYPE')=='branch' and
            not os.environ.get('GITHUB_HEAD_REF') and not os.environ.get('GITHUB_BASE_REF') and
            os.environ.get('INPUT_NATIVE')=='true','CONTROL_CONTEXT')
    require(command(['status','--porcelain=v1','--untracked-files=all'],source).stdout==b'','SOURCE_DIRTY')
    require(command(['rev-parse','HEAD'],source).stdout.decode().strip()==binding['commit'],'SOURCE_COMMIT')
    require(command(['rev-parse','--abbrev-ref','HEAD'],source).stdout==b'HEAD\n','SOURCE_DETACHED')
    origin=command(['remote','get-url','origin'],source).stdout.decode().strip()
    require(origin in ('https://github.com/'+binding['repository'],
                       'https://github.com/'+binding['repository']+'.git'),'SOURCE_ORIGIN')
    rows=inventory(source)
    require(rows==binding['inventory'] and digest(rows)==binding['inventory_sha256'],'SOURCE_INVENTORY')
    value={'schema':1,'repository':binding['repository'],'commit':binding['commit'],
           'inventory_sha256':binding['inventory_sha256'],'files':len(rows),'authority':AUTHORITY,
           'provider_requests':0,'verified':True}
    receipt=Path(receipt);fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as stream:stream.write(canonical(value));stream.flush();os.fsync(stream.fileno())
    return value

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--binding',dest='binding_path',required=True);parser.add_argument('--source',required=True);parser.add_argument('--receipt',required=True)
    print(canonical(verify(**vars(parser.parse_args()))).decode(),end='')

if __name__=='__main__':main()
