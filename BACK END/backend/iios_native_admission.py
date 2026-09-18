"""Admission compiler. Legacy roots or incomplete native bindings cannot execute."""
import hashlib
import json
import os
import time
from pathlib import Path
from iios_native_conductor import STAGES,QualificationFailure,require,pin_file,digest,AUTHORITIES,failure

ADAPTERS=dict(zip(STAGES[4:9],('iios_native_assembly.py','iios_native_static.py','iios_native_image_policy.py','iios_native_runtime_adapter.py','iios_native_lifecycle.py')))
REQUIRED_NATIVE = tuple(ADAPTERS)


def admit_source(manifest):
    source=manifest['source'];require(source['commit']==manifest['ci']['commit'],STAGES[0],'CI_EXACT_COMMIT')
    pin_file(manifest['ci']['path'],manifest['ci']['sha256'])
    ci=json.loads(Path(manifest['ci']['path']).read_bytes())
    require(ci['source']==source['commit'] and ci['status']=='GREEN' and ci['artifact_hashes_verified'] is True and ci['native_execution'] is False,STAGES[0],'CI_GREEN_PREPARATION')
    for row in source['inventory']:
        require(not Path(row['relative']).is_absolute() and '..' not in Path(row['relative']).parts,STAGES[0],'SOURCE_INVENTORY_PATH')
        pin_file(Path(source['root'])/row['relative'],row['sha256'])
    for row in manifest['inputs']:pin_file(row['path'],row['sha256'])
    for row in manifest['historical_records']:pin_file(row['path'],row['sha256'])
    return True


def review_bindings(manifest):
    """No implicit legacy command substitution, invented capabilities, or skips."""
    blockers=[]
    for row in manifest['stages']:
        if row['id'] not in REQUIRED_NATIVE:continue
        binding=row.get('native_binding')
        if not binding:
            blockers.append({'stage':row['id'],'predicate':'NATIVE_ADAPTER_BINDING_REQUIRED','expected':'REVIEWED_FRESH_ROOT_ADAPTER','observed':'MISSING','exception_subtype':'NONE','errno_category':'NONE'});continue
        required={'adapter_path','adapter_sha256','command','input_parents','expected_outputs','ownership_contract','outer_budget_contract','failure_protocol','review_parent'}
        if set(binding)!=required:
            blockers.append({'stage':row['id'],'predicate':'NATIVE_ADAPTER_SCHEMA','expected':'COMPLETE','observed':'INCOMPLETE','exception_subtype':'NONE','errno_category':'NONE'});continue
        if binding['outer_budget_contract']!='INHERIT_OUTER_DEADLINE_V1' or binding['failure_protocol']!='SANITIZED_STAGE_FAILURE_V1':
            blockers.append({'stage':row['id'],'predicate':'NATIVE_ADAPTER_PROTOCOL','expected':'SHARED_DEADLINE_AND_EXACT_FAILURES','observed':'INCOMPATIBLE','exception_subtype':'NONE','errno_category':'NONE'})
        elif not binding['ownership_contract'] or not binding['review_parent'] or not binding['expected_outputs']:
            blockers.append({'stage':row['id'],'predicate':'NATIVE_ADAPTER_REVIEW','expected':'COMPLETE','observed':'INCOMPLETE','exception_subtype':'NONE','errno_category':'NONE'})
        else:
            relative='BACK END/backend/'+ADAPTERS[row['id']]
            inventory={r['relative']:r['sha256'] for r in manifest['source']['inventory']}
            expected=str(Path(manifest['source']['root'])/relative)
            if binding['adapter_path']!=expected or inventory.get(relative)!=binding['adapter_sha256']:
                blockers.append({'stage':row['id'],'predicate':'SOURCE_CONTROLLED_ADAPTER_REQUIRED','expected':'EXACT_STAGE_IMPLEMENTATION','observed':'SUBSTITUTED_OR_MISSING','exception_subtype':'NONE','errno_category':'NONE'})
            else:pin_file(binding['adapter_path'],binding['adapter_sha256'])
    return blockers


def require_execution_ready(manifest):
    blockers=review_bindings(manifest)
    if blockers:
        item=blockers[0]
        raise QualificationFailure(item['stage'],item['predicate'],item['expected'],item['observed'])
    require(manifest.get('native_execution_ready') is True,STAGES[0],'NATIVE_EXECUTION_READY','REVIEWED','BLOCKED')
    from iios_native_ownership import unresolved_binding
    unresolved_binding(manifest)
    require(manifest.get('environment')=={'LC_ALL':'C','TZ':'UTC','__CF_USER_TEXT_ENCODING':'0x1F5:0x0:0x0'},STAGES[0],'OWNED_EXACT_ENVIRONMENT')
    lifecycle=manifest.get('native',{}).get('lifecycle',{})
    require('profile_review' in lifecycle and 'profile_template' in lifecycle,STAGES[0],'LIFECYCLE_PROFILE_REVIEW_REQUIRED','PINNED_REVIEW','MISSING')
    require(lifecycle.get('environment')=={'LANG':'C','LC_ALL':'C','TZ':'UTC'},STAGES[0],'LIFECYCLE_EXACT_ENVIRONMENT')
    from iios_native_profile import reviewed_profile
    execution=Path(manifest['output_parent'])/manifest['output_name']/'payload/assembly-output/execution-01'
    roots={k:str(execution/v) for k,v in {'runtime':'output/runtime-pilot','release':'release','control':'control','output':'disposable'}.items()}
    reviewed_profile(manifest,lifecycle,roots)
    import plistlib
    identity=manifest.get('os_identity',{})
    require(identity.get('path')=='/System/Library/CoreServices/SystemVersion.plist',STAGES[0],'OS_BUILD_IDENTITY_PATH')
    pin_file(identity['path'],identity['sha256'])
    require(plistlib.loads(Path(identity['path']).read_bytes()).get('ProductBuildVersion')==manifest['os_build'],STAGES[0],'OS_BUILD_IDENTITY')


def terminal_categories(term,ttys,forbidden_markers,host,expected_host):
    stage=STAGES[1]
    require(term=='Apple_Terminal',stage,'TERMINAL_APPLICATION','APPLE_TERMINAL','OTHER_CONTEXT')
    require(len(ttys)==3 and all(ttys),stage,'TERMINAL_TTY','ALL_TTY','NOT_ALL_TTY')
    require(not forbidden_markers,stage,'TERMINAL_FORBIDDEN_MARKERS','ABSENT','PRESENT')
    require(host==expected_host,stage,'HOST_BINDING','EXACT','MISMATCH')
    return True


def render_terminal_launcher(argv,cwd,checks):
    """Source-controlled launcher bytes; generation never executes the command."""
    import shlex
    require(type(argv) is list and len(argv)==10 and argv[1:3]==['-I','-B'] and argv[4]=='--manifest'
            and argv[6]=='--manifest-sha256' and argv[8]=='--authorize-manifest' and argv[7]==argv[9],STAGES[0],'LAUNCHER_COMMAND_SHAPE')
    require(type(cwd) is str and Path(cwd).is_absolute(),STAGES[0],'LAUNCHER_CWD')
    require(all(type(v) is str and '\n' not in v and '\0' not in v for v in argv),STAGES[0],'LAUNCHER_ARGV')
    require({argv[0],argv[3],argv[5]} <= {r['path'] for r in checks},STAGES[0],'LAUNCHER_CHECKS')
    shell="""#!/bin/zsh -f
set -eu
[[ $# -eq 0 ]] || { print -r -- 'RED LAUNCH_ARGUMENTS'; exit 1; }
[[ ${TERM_PROGRAM-} == Apple_Terminal && -t 0 && -t 1 && -t 2 ]] || { print -r -- 'RED TERMINAL_ADMISSION'; exit 1; }
[[ -z ${VSCODE_PID+x}${VSCODE_IPC_HOOK_CLI+x}${CODEX_THREAD_ID+x}${CODEX_SANDBOX_NETWORK_DISABLED+x} ]] || { print -r -- 'RED TERMINAL_CONTEXT'; exit 1; }
verify_pin() {
  [[ -f "$1" && ! -L "$1" ]] || { print -r -- 'RED LAUNCH_INPUT_TYPE'; exit 1; }
  local observed
  observed=$(/usr/bin/shasum -a 256 -- "$1") || { print -r -- 'RED LAUNCH_HASH_READ'; exit 1; }
  [[ ${observed%% *} == "$2" ]] || { print -r -- 'RED LAUNCH_HASH_MISMATCH'; exit 1; }
}
"""
    for row in checks:
        require(type(row['path']) is str and Path(row['path']).is_absolute() and
                type(row['sha256']) is str and len(row['sha256'])==64 and all(c in '0123456789abcdef' for c in row['sha256']),STAGES[0],'LAUNCHER_PIN')
        shell+='verify_pin '+shlex.quote(row['path'])+' '+shlex.quote(row['sha256'])+'\n'
    return (shell+'cd -- '+shlex.quote(cwd)+'\nexec '+shlex.join(argv)+'\n').encode()
