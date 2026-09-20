#!/usr/bin/env python3
"""Offline macOS regression through the real environment and Mach-O toolchain.

Uses a fresh disposable runtime, exact local locked wheels and the pinned vendor
framework. Does not launch the qualification app, workers or providers.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--wheelhouse',required=True,type=Path)
    args=parser.parse_args()
    source=Path(__file__).resolve().parents[1]
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(source/'BACK END/backend'))
    from iios_qualification_v2 import runtime
    from iios_qualification_v2.state import decode,directory,file_hash,publish,require
    from iios_qualification_v2.roots import binding,contained
    bound=binding()
    parent=contained(Path(bound['root'])/'qualification',bound)
    root=Path(tempfile.mkdtemp(prefix='native-dependency-regression-',dir=parent))
    runtime_root=directory(root/'runtime');cwd=directory(root/'source-cwd')
    wheels=directory(runtime_root/'wheelhouse')
    lock=source/'config/production-python-requirements.lock'
    artifacts=source/'config/production-python-artifacts.lock.json'
    pins=runtime.lock_binding(lock,artifacts)
    for pin in pins['wheels']:
        original=args.wheelhouse/pin['filename']
        require(not original.is_symlink(),'REGRESSION_WHEEL_SYMLINK')
        runtime.verify_wheel(original,pin)
        shutil.copyfile(original,wheels/pin['filename'])
        (wheels/pin['filename']).chmod(0o400)
    config=runtime.bind_vendor_framework_contract(source,decode((source/'config/native-qualification-v2.json').read_bytes()))
    source_hash=file_hash(Path(runtime.__file__))
    def offline(event,args):
        if event.startswith('socket.'):
            raise PermissionError('REGRESSION_NETWORK_FORBIDDEN')
    sys.addaudithook(offline)
    original_command=runtime.command
    originals={name:getattr(Path,name) for name in ('resolve','stat','lstat')}
    metadata_access=[];observed=[];scenario='';injections=0
    def traced_command(argv,**kwargs):
        nonlocal injections
        output=original_command(argv,**kwargs)
        if list(map(str,argv[:2]))==['/usr/bin/otool','-l'] and 'bazel-out/' in output:
            require('LC_ID_DYLIB' in output,'REGRESSION_ID_MISSING')
            observed.append(dict(scenario=scenario,image=str(argv[2]),sha256=file_hash(argv[2]),otool_sha256=hashlib.sha256(output.encode()).hexdigest()))
            if scenario=='name_injected_then_absent':
                # Reproduce disappearance after enumeration, before parser resolution.
                os.mkdir(cwd/'bazel-out',0o700);os.rmdir(cwd/'bazel-out');injections+=1
        return output
    def instrument(name):
        def traced(path,*args,**kwargs):
            if 'bazel-out' in path.parts:
                metadata_access.append(dict(operation=name,path=str(path)))
                raise AssertionError('INSTALL_NAME_USED_AS_FILESYSTEM_PATH')
            return originals[name](path,*args,**kwargs)
        return traced
    runtime.command=traced_command
    results=[];old_cwd=Path.cwd()
    try:
        os.chdir(cwd)
        for name in originals:setattr(Path,name,instrument(name))
        for scenario in ('bazel_out_absent','name_injected_then_absent'):
            result=runtime.environment(runtime_root,config,lock,artifacts)
            native=result['manifest']['native']
            upb=[rows for name,rows in native.items() if name.endswith('/google/_upb/_message.abi3.so')]
            require(len(upb)==1 and len(upb[0])==6,'REGRESSION_EXACT_IMAGE_LOADS')
            require({row['architecture'] for row in upb[0]}=={'arm64','x86_64'},'REGRESSION_ARCHITECTURES')
            require(all(row['kind']=='OS_SHARED_CACHE' and row['command']=='LC_LOAD_DYLIB' for row in upb[0]),'REGRESSION_DEPENDENCIES')
            require(not any('bazel-out' in row['load'] for rows in native.values() for row in rows),'REGRESSION_METADATA_LEAK')
            results.append(dict(scenario=scenario,status='PASS',native_images=len(native),manifest_sha256=result['manifest_sha256']))
    finally:
        for name,original in originals.items():setattr(Path,name,original)
        runtime.command=original_command;os.chdir(old_cwd)
    require(injections>0 and not metadata_access,'REGRESSION_NOT_EXERCISED')
    require({row['scenario'] for row in observed}=={row['scenario'] for row in results},'REGRESSION_SCENARIOS')
    require(results[0]['manifest_sha256']==results[1]['manifest_sha256'],'REGRESSION_RUNTIME_DRIFT')
    require(source_hash==file_hash(Path(runtime.__file__)),'REGRESSION_SOURCE_CHANGED')
    report=dict(status='PASS',source_root=str(source),runtime_file=str(Path(runtime.__file__)),runtime_sha256=source_hash,
                scenarios=results,observed_images=observed,metadata_filesystem_access=metadata_access,
                disappearance_injections=injections,provider_requests=0,app_launched=False,
                authority=dict(broker_connection=False,paper_order_permission=False,trade_execution=False,live_execution=False))
    publish(root/'report.json',report)
    print(json.dumps(dict(report=str(root/'report.json'),**report),sort_keys=True))


if __name__=='__main__':main()
