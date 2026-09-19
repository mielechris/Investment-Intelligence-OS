#!/usr/bin/env python3
"""Build an exclusive private-control repository candidate from one clean commit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

SOURCE_REPOSITORY='mielechris/Investment-Intelligence-OS'
CONTROL_REPOSITORY='mielechris/IIOS-Native-Control'
AUTHORITY={'broker_connection':False,'paper_order_permission':False,
           'trade_execution':False,'live_execution':False}

def require(value,code):
    if not value:raise ValueError(code)

def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    source=Path(__file__).resolve().parents[1];sys.path.insert(0,str(source/'BACK END/backend'))
    from iios_qualification_v2.runtime import source_identity
    identity=source_identity(source);output=Path(args.output)
    require(output.parent==Path.home()/'Library/IIOS/qualification','CONTROL_OUTPUT_ROOT')
    output.mkdir(mode=0o700)
    template=source/'native-control'
    for path in sorted(template.rglob('*')):
        if path.is_dir():continue
        relative=path.relative_to(template)
        if path.name.endswith('.in'):continue
        destination=output/relative;destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        shutil.copyfile(path,destination);destination.chmod(0o700 if os.access(path,os.X_OK) else 0o600)
    workflow=(template/'.github/workflows/native-qualification.yml.in').read_text()
    workflow=workflow.replace('@@SOURCE_REPOSITORY@@',SOURCE_REPOSITORY).replace('@@SOURCE_COMMIT@@',identity['commit'])
    destination=output/'.github/workflows/native-qualification.yml';destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    destination.write_text(workflow);destination.chmod(0o600)
    binding={'schema':1,'repository':SOURCE_REPOSITORY,'commit':identity['commit'],
             'inventory':identity['inventory'],'inventory_sha256':identity['inventory_sha256'],'authority':AUTHORITY}
    (output/'config/source-binding.json').write_bytes(canonical(binding));(output/'config/source-binding.json').chmod(0o600)
    readme=(source/'native-control/README.md.in').read_text().replace('@@SOURCE_COMMIT@@',identity['commit']).replace('@@SOURCE_INVENTORY_SHA256@@',identity['inventory_sha256'])
    (output/'README.md').write_text(readme);(output/'README.md').chmod(0o600)
    files={}
    for path in sorted(output.rglob('*')):
        if path.is_file():files[str(path.relative_to(output))]={'bytes':path.stat().st_size,'sha256':sha(path)}
    (output/'CONTROL-FILES.json').write_bytes(canonical({'schema':1,'repository':CONTROL_REPOSITORY,'files':files,'authority':AUTHORITY}))
    (output/'CONTROL-FILES.json').chmod(0o400)
    print(canonical({'status':'PREPARED_NOT_CREATED','path':str(output),'source_commit':identity['commit'],
                     'source_inventory_sha256':identity['inventory_sha256'],'files':len(files)+1,
                     'authority':AUTHORITY}).decode(),end='')

if __name__=='__main__':main()
