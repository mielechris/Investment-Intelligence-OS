"""Inert, separately scoped disposable-role bindings; never live admission.

The native test entrypoint verifies files and host evidence before constructing
this capability. Live entrypoints still require exact ObservationExecution.
"""
from copy import deepcopy
import json
from pathlib import PurePosixPath
import re
from alpha_session_contract import require, instant
from provider_gateway_contract import canonical, content_hash, locked_authority, pin, safe_document

SCOPE = 'DISPOSABLE_NATIVE_QUALIFICATION_ONLY'
SCHEMA = 'iios-disposable-observation-roles-v1'
MODULE = 'alpha_observation_qualification'


class DisposableRoles:
    __slots__ = ('_body', '_parent', '_roots')
    def __init__(self, *args, **kwargs):
        raise TypeError('DISPOSABLE_FACTORY_REQUIRED')
    def __setattr__(self, name, value):
        raise AttributeError('DISPOSABLE_IMMUTABLE')
    @property
    def identity(self):return self._parent
    def document(self):return json.loads(self._body)
    def recheck(self, now):
        value=admit_roles(self.document(), self.identity, approved_roots=json.loads(self._roots), now=now)
        from alpha_session_evidence import verify_files
        d=value.document()
        if d['schema']=='iios-disposable-observation-roles-v3':
            import os,stat
            from iios_native_evidence import owned_directory
            fd=owned_directory(d['conductor']['output_root'])
            try:
                st=os.fstat(fd)
                require([st.st_dev,st.st_ino,st.st_uid,stat.S_IMODE(st.st_mode)]==d['conductor']['output_identity'],'DISPOSABLE_CONDUCTOR_ROOT_REPLACED')
            finally:os.close(fd)
        for key,rows in [('runtime',d['runtime']['files']),('release',d['input_files']['release']),('control',d['input_files']['control'])]:
            if key == 'runtime' and d['schema'] in ('iios-disposable-observation-roles-v2','iios-disposable-observation-roles-v3'):
                from alpha_runtime_files import verify_runtime_tree, extension
                verify_runtime_tree(d['roots'][key],rows,approved_root=d['roots'][key],**extension(d['runtime']))
            else:
                verify_files(d['roots'][key],rows,approved_root=d['roots'][key])
        return value


def admit_roles(document, expected, *, approved_roots, now):
    """Pure exact descriptor admission, explicitly not provenance qualification."""
    from alpha_runtime_files import safe_runtime_envelope
    safe_runtime_envelope(document);pin(document,expected)
    d=document
    conductor_version=d.get('schema')=='iios-disposable-observation-roles-v3'
    fields={'schema','scope','source_commit','roots','release_parent',
        'runtime_parent','runtime','launch','input_files','control_parent','seed_parents','valid_from','expires_at','authority'}
    require(type(d) is dict and set(d)==fields|({'conductor'} if conductor_version else set()),'DISPOSABLE_SCHEMA')
    if conductor_version:
        b=d['conductor']
        require(type(b) is dict and set(b)=={'manifest','source','runtime_reference','runtime_acceptance','host','output_root','output_identity','execution_root','process_image','clock_basis','inspection_tools'},'DISPOSABLE_CONDUCTOR_SCHEMA')
        require(b['source']==d['source_commit'] and all(type(b[k]) is str and re.fullmatch('[0-9a-f]{64}',b[k]) for k in ('manifest','runtime_reference','runtime_acceptance','host')),'DISPOSABLE_CONDUCTOR_PARENTS')
        require(type(b['inspection_tools']) is dict and set(b['inspection_tools'])=={'/bin/ps','/usr/sbin/lsof'} and all(type(v) is str and re.fullmatch('[0-9a-f]{64}',v) for v in b['inspection_tools'].values()),'DISPOSABLE_INSPECTION_TOOLS')
        require(b['clock_basis']=='DARWIN_CLOCK_MONOTONIC_RAW_NS','DISPOSABLE_CLOCK_BASIS')
        root=PurePosixPath(b['output_root'])
        require(root.is_absolute() and root.name.startswith('qualification-') and '..' not in root.parts and
            b['execution_root']==str(root/'payload/assembly-output/execution-01'),'DISPOSABLE_CONDUCTOR_ROOT')
        require(type(b['output_identity']) is list and len(b['output_identity'])==4 and all(type(x) is int for x in b['output_identity']) and b['output_identity'][3]==0o700,'DISPOSABLE_CONDUCTOR_IDENTITY')
    require(d['schema'] in (SCHEMA,'iios-disposable-observation-roles-v2','iios-disposable-observation-roles-v3') and d['scope']==SCOPE and re.fullmatch('[0-9a-f]{40}',d['source_commit']),
        'DISPOSABLE_SCOPE')
    require(type(approved_roots) is dict and set(approved_roots)=={'runtime','release','control','output'} and
        d['roots']==approved_roots,'DISPOSABLE_ROOTS')
    paths=[];execution_roots=[]
    for kind,raw in approved_roots.items():
        require(type(raw) is str and raw.startswith('/') and
            '\x00' not in raw and '//' not in raw and not raw.endswith('/'),'DISPOSABLE_PATH')
        p=PurePosixPath(raw)
        if kind=='runtime':
            require(p.name=='runtime-pilot' and p.parent.name=='output','DISPOSABLE_RUNTIME_DESTINATION')
            execution=p.parent.parent
        else:
            require(p.name=={'release':'release','control':'control','output':'disposable'}[kind],'DISPOSABLE_DESTINATION')
            execution=p.parent
        require((str(execution)==d['conductor']['execution_root'] if conductor_version else execution.name=='execution-01' and execution.parent.name.startswith('iios-provider-connection-source-tests-')),
            'DISPOSABLE_ARTIFACT_PARENT')
        execution_roots.append(execution)
        require(str(p)==raw and '..' not in p.parts and not any(x.startswith('~') or
            x.lower() in {'keychains','ledger','ledgers','credentials','application support'} for x in p.parts),
            'DISPOSABLE_PATH')
        paths.append(p)
    require(len(set(execution_roots))==1,'DISPOSABLE_EXECUTION_PARENT')
    require(all(not a.is_relative_to(b) and not b.is_relative_to(a) for i,a in enumerate(paths) for b in paths[i+1:]),
        'DISPOSABLE_ROOT_ALIAS')
    require(instant(d['valid_from'])<=now<instant(d['expires_at']) and
        0<(instant(d['expires_at'])-instant(d['valid_from'])).total_seconds()<=900,'DISPOSABLE_WINDOW')
    for k in ('release_parent','runtime_parent','control_parent'):
        require(type(d[k]) is str and re.fullmatch('[0-9a-f]{64}',d[k]),'DISPOSABLE_PIN')
    require(type(d['input_files']) is dict and set(d['input_files'])=={'release','control'} and
        content_hash(d['input_files']['release'])==d['release_parent'] and
        content_hash(d['input_files']['control'])==d['control_parent'],'DISPOSABLE_INPUT_PARENTS')
    require({r['path'] for r in d['input_files']['control']}=={'profile.sb','loopback.crt','loopback.pem'},'DISPOSABLE_CONTROL')
    require({'alpha_observation_qualification.py','truth_spine_full_day_runner.py','truth_spine_full_day_service.py'} <=
        {r['path'] for r in d['input_files']['release']},'DISPOSABLE_ENTRYPOINTS')
    from alpha_runtime_files import (DESCRIPTOR_SCHEMA, COMPLETED_DESCRIPTOR_SCHEMA, EXTENSION_FIELDS,
        extension, _validate_rows, verify_completed_descriptor)
    version2 = d['schema'] in ('iios-disposable-observation-roles-v2','iios-disposable-observation-roles-v3')
    rt=d['runtime']
    version3=rt.get('schema')==COMPLETED_DESCRIPTOR_SCHEMA
    if version2:
        require(rt.get('schema') in (DESCRIPTOR_SCHEMA,COMPLETED_DESCRIPTOR_SCHEMA),'DISPOSABLE_RUNTIME_VERSION')
        extension(rt)
        _validate_rows(rt['files'],rt['metadata'],{x['path']:x['target'] for x in rt['layout_policy']['links']})
    require(type(rt) is dict and set(rt)==({'root','interpreter','files'} |
        ({'schema'} | EXTENSION_FIELDS if version2 else set()) | ({'completed_manifest'} if version3 else set())) and
        rt['root']==approved_roots['runtime'] and rt['interpreter']=='bin/python3.14','DISPOSABLE_RUNTIME')
    require(type(rt['files']) is list and bool(rt['files']) and content_hash(rt)==d['runtime_parent'],
        'DISPOSABLE_RUNTIME_PARENT')
    def inventory(rows):
        require(type(rows) is list and bool(rows),'DISPOSABLE_INPUT_FILES')
        seen=set()
        for row in rows:
            require(type(row) is dict and set(row)=={'path','size','mode','sha256'} and type(row['path']) is str,
                'DISPOSABLE_RUNTIME_FILE')
            p=PurePosixPath(row['path'])
            require(not p.is_absolute() and str(p)==row['path'] and p.parts and '..' not in p.parts and
                '\x00' not in row['path'] and row['path'] not in seen and type(row['size']) is int and row['size']>=0 and
                type(row['mode']) is int and row['mode'] in (0o400,0o500) and type(row['sha256']) is str and
                re.fullmatch('[0-9a-f]{64}',row['sha256']), 'DISPOSABLE_RUNTIME_FILE')
            seen.add(row['path'])
        return seen
    require(rt['interpreter'] in inventory(rt['files']),'DISPOSABLE_INTERPRETER')
    if conductor_version:
        image=d['conductor']['process_image']
        require(type(image) is dict and set(image)=={'path','sha256'} and image in [{'path':str(PurePosixPath(rt['root'])/r['path']),'sha256':r['sha256']} for r in rt['files']],'DISPOSABLE_PROCESS_IMAGE_PIN')
    if version3:
        require(version2,'DISPOSABLE_RUNTIME_VERSION')
        verify_completed_descriptor(rt,source_commit=d['source_commit'])
    for rows in d['input_files'].values():inventory(rows)
    launch=d['launch']
    require(type(launch) is dict and set(launch)=={'host','port','peer_hash','sandbox_hash','host_identity',
        'start_ns','startup_ns','stop_ns','final_ns'},'DISPOSABLE_LAUNCH')
    require(launch['host']=='127.0.0.1' and type(launch['port']) is int and 1024<launch['port']<65536,
        'DISPOSABLE_ENDPOINT')
    require(all(type(launch[k]) is str and re.fullmatch('[0-9a-f]{64}',launch[k]) for k in ('peer_hash','sandbox_hash')),
        'DISPOSABLE_TLS_PIN')
    host=launch['host_identity']
    require(type(host) is dict and set(host)=={'system','release','version','machine','uid'} and
        host['system']=='Darwin' and host['machine']=='arm64' and type(host['uid']) is int and host['uid']>0,
        'DISPOSABLE_HOST')
    keys=('start_ns','startup_ns','stop_ns','final_ns')
    require(all(type(launch[k]) is int and 0<launch[k]<2**63 for k in keys) and
        launch['start_ns']<launch['startup_ns']<launch['stop_ns']<launch['final_ns'] and
        launch['startup_ns']-launch['start_ns']<=60_000_000_000 and
        launch['final_ns']-launch['start_ns']<=780_000_000_000 and
        launch['final_ns']-launch['stop_ns']>=120_000_000_000,'DISPOSABLE_BUDGET')
    require(type(d['seed_parents']) is list and len(d['seed_parents'])==3 and
        len(set(d['seed_parents']))==3 and all(type(x) is str and re.fullmatch('[0-9a-f]{64}',x) for x in d['seed_parents']),
        'DISPOSABLE_SEED_PINS')
    require(d['authority']==locked_authority() and all(v is False for v in d['authority'].values()),'DISPOSABLE_AUTHORITY')
    v=object.__new__(DisposableRoles)
    object.__setattr__(v,'_body',canonical(deepcopy(d)));object.__setattr__(v,'_parent',expected)
    object.__setattr__(v,'_roots',canonical(approved_roots))
    return v


def disposable(capability):return type(capability) is DisposableRoles


def role_scope(capability):
    if disposable(capability):return SCOPE
    from alpha_observation_lifecycle import ObservationExecution, EXECUTION_SCOPE
    require(type(capability) is ObservationExecution,'OBSERVATION_CAPABILITY_REQUIRED')
    return EXECUTION_SCOPE


def record(capability, value):
    role_scope(capability)
    if not disposable(capability):return value
    return dict(value,scope=SCOPE,production_qualified=False,provider_access=False,credential_access=False,
        seeded=True,requests_attempted=0,broker_connected=False,paper_order_permission=False,
        trade_execution_permission=False,live_execution=False)


def seed(slot, previous):
    require(type(slot) is int and 0<=slot<3,'DISPOSABLE_SEED_SLOT')
    return dict(schema='iios-disposable-role-seed-v1',scope=SCOPE,slot=slot,previous=previous,
        seeded=True,executed_requests=0,authority=locked_authority())


def seed_projection(capability, plan, *, records, now):
    """Validate independently pinned seed records; never count live requests."""
    require(disposable(capability),'DISPOSABLE_CAPABILITY_REQUIRED');capability.recheck(now)
    d=capability.document();previous=None
    require(type(records) is list and len(records)==3 and set(plan)=={'session','seed_parents'} and
        plan['seed_parents']==d['seed_parents'],'DISPOSABLE_SEEDS')
    for i,row in enumerate(records):
        require(row==seed(i,previous),'DISPOSABLE_SEED_BINDING');pin(row,d['seed_parents'][i]);previous=content_hash(row)
    return record(capability,dict(schema='iios-truth-observation-projection-v1',admission_parent=capability.identity,
        source_commit=d['source_commit'],session=plan['session'],plan_parent=content_hash(plan),
        request_parents=[],response_parents=d['seed_parents'],completion_parent=previous,
        reserved=0,completed=0,seeded_records=3,status='COMPLETE',published_at=now.isoformat(),
        coverage='DISPOSABLE_SEEDS_ONLY',freshness='NOT_PROVIDER_EVIDENCE',governance='NOT_EXECUTED',
        authority=locked_authority()))


def configuration(capability):
    """Deterministically bind the entire child configuration to its capability."""
    from datetime import timedelta
    require(disposable(capability),'DISPOSABLE_CAPABILITY_REQUIRED')
    d=capability.document();delta=d['launch']['startup_ns']-d['launch']['start_ns']
    require(delta%1000==0,'DISPOSABLE_UTC_PRECISION')
    plan=dict(session='DISPOSABLE',seed_parents=d['seed_parents'],startup_not_before=d['valid_from'],
        startup_deadline=(instant(d['valid_from'])+timedelta(microseconds=delta//1000)).isoformat())
    return dict(schema='iios-disposable-role-config-v1',admission=d,admission_parent=capability.identity,
        roots=d['roots'],plan=plan,requests=[{'runtime':d['runtime']} for _ in range(3)],request_pins=[])


def invocation_pins(capability):
    require(disposable(capability),'DISPOSABLE_CAPABILITY_REQUIRED')
    return ['--config-sha256',content_hash(configuration(capability)),'--approved-roots-json',
        json.dumps(capability.document()['roots'],sort_keys=True,separators=(',',':'))]


def bind_conductor_clock(capability):
    """Use the already authorized outer clock in this disposable process only.

    No deadline is recomputed. Every existing Truth Spine absolute nanosecond
    check reads the same Darwin clock as the conductor. Legacy scopes retain
    their original clock unchanged.
    """
    require(disposable(capability),'DISPOSABLE_CAPABILITY_REQUIRED')
    if capability.document()['schema']!='iios-disposable-observation-roles-v3':return
    require(capability.document()['conductor']['clock_basis']=='DARWIN_CLOCK_MONOTONIC_RAW_NS','DISPOSABLE_CLOCK_BASIS')
    import time
    clock=time.clock_gettime_ns
    time.monotonic_ns=lambda:clock(6)
