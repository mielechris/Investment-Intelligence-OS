"""Admission compiler. Legacy roots or incomplete native bindings cannot execute."""
import hashlib
import json
import os
import time
from pathlib import Path
from iios_native_conductor import STAGES,QualificationFailure,require,pin_file,digest,AUTHORITIES,failure

# Source-controlled gate: a manifest cannot authorize an unfinished dispatcher.
NATIVE_DISPATCHER_READY = False

REQUIRED_NATIVE = (STAGES[4],STAGES[5],STAGES[6],STAGES[7])


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
            pin_file(binding['adapter_path'],binding['adapter_sha256'])
    if manifest.get('native',{}).get('runtime_reference') is None:
        blockers.append({'stage':STAGES[6],'predicate':'FINAL_RUNTIME_IMAGE_REFERENCE_REQUIRED','expected':'INDEPENDENT_FINAL_RUNTIME_REFERENCE','observed':'MISSING','exception_subtype':'NONE','errno_category':'NONE'})
    else:
        from iios_native_runtime_reference import admit_reference
        try:
            context=manifest['native'].get('runtime_reference_context')
            require(type(context) is dict and set(context)=={'source','root','host','layout_parent','policy','imports'},STAGES[6],'FINAL_RUNTIME_REFERENCE_CONTEXT')
            require(context['source']==manifest['source']['commit'],STAGES[6],'FINAL_RUNTIME_REFERENCE_SOURCE')
            admit_reference(manifest['native']['runtime_reference'],now=time.time(),**context)
        except Exception as error:
            blockers.append(failure(error,STAGES[6],'FINAL_RUNTIME_REFERENCE_ADMISSION'))
    if not NATIVE_DISPATCHER_READY:
        blockers.append({'stage':STAGES[0],'predicate':'NATIVE_DISPATCHER_INTEGRATION_REQUIRED','expected':'COMPLETE_REVIEWED_IMPLEMENTATION','observed':'INCOMPLETE','exception_subtype':'NONE','errno_category':'NONE'})
    return blockers


def require_execution_ready(manifest):
    blockers=review_bindings(manifest)
    if blockers:
        item=blockers[0]
        raise QualificationFailure(item['stage'],item['predicate'],item['expected'],item['observed'])
    require(manifest.get('native_execution_ready') is True,STAGES[0],'NATIVE_EXECUTION_READY','REVIEWED','BLOCKED')


def terminal_categories(term,ttys,forbidden_markers,host,expected_host):
    stage=STAGES[1]
    require(term=='Apple_Terminal',stage,'TERMINAL_APPLICATION','APPLE_TERMINAL','OTHER_CONTEXT')
    require(len(ttys)==3 and all(ttys),stage,'TERMINAL_TTY','ALL_TTY','NOT_ALL_TTY')
    require(not forbidden_markers,stage,'TERMINAL_FORBIDDEN_MARKERS','ABSENT','PRESENT')
    require(host==expected_host,stage,'HOST_BINDING','EXACT','MISMATCH')
    return True
