"""Independent production image universe and complete two-scan acceptance.

Only admitted static inputs construct trust. Dynamic observations cannot add an
image, change the import plan, expand bounds, or establish mapped-memory trust.
The accepted bootstrap contract remains a distinct, immutable payload.
"""
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
from iios_native_conductor import require, digest, canonical, pin_file, STAGES
from iios_native_macho import image_uuid

BOOTSTRAP='BOOTSTRAP_IMAGE_REFERENCE_V1'
PRODUCTION='PRODUCTION_RUNTIME_IMAGE_POLICY_V1'
STAGE=STAGES[6]
HEX=re.compile(r'[0-9a-f]{64}\Z')
UUID=re.compile(r'[0-9a-f]{32}\Z')
IMPORT=re.compile(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\Z')
MAX_IMAGES=4096
MAX_REPORT_BYTES=4*1024*1024
LOADS={'LC_LOAD_DYLIB','LC_LOAD_WEAK_DYLIB','LC_REEXPORT_DYLIB','LC_LOAD_UPWARD_DYLIB','LC_LAZY_LOAD_DYLIB'}


def need(ok,predicate):require(ok,STAGE,predicate)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def forbidden(value):
    # Match path/import components, not innocent substrings such as "stock".
    return any(re.fullmatch(r'(?:_?tkinter|(?:lib)?(?:tcl|tk))(?:[.\-0-9].*)?',part.lower()) for part in re.split(r'[/\\]',value))
def path(value,absolute=True):
    need(type(value) is str and 0<len(value)<=4096 and '\0' not in value and '\\' not in value,'IMAGE_PATH')
    p=PurePosixPath(value)
    need(p.is_absolute()==absolute and str(p)==value and '..' not in p.parts and not value.startswith('//'),'IMAGE_PATH')
    need(not forbidden(value),'PRODUCTION_FORBIDDEN_COMPONENT')
    return value

def hash_value(value):need(type(value) is str and HEX.fullmatch(value),'IMAGE_HASH')
def uuid_value(value):need(type(value) is str and UUID.fullmatch(value) and value!='0'*32,'IMAGE_UUID')


def bootstrap_scope(reference,*,payload_sha256,interpreter,interpreter_sha256):
    """A new scope envelope preserves the legacy 557-image payload byte-for-byte.

    The caller pins the original bytes separately; the payload never becomes a
    production policy and cannot be rebased to the sealed production root.
    """
    need(type(reference) is bytes and sha(reference)==payload_sha256,'BOOTSTRAP_REFERENCE_HASH')
    value=json.loads(reference)
    need(value.get('schema')=='SCOPED_BOOTSTRAP_IMAGE_REFERENCE_V1','BOOTSTRAP_REFERENCE_SCOPE')
    need(value.get('expected_count')==value.get('image_maximum')==557 and len(value.get('ordered_rows',[]))==557,'BOOTSTRAP_557_CONTRACT')
    rows=value['ordered_rows']
    need([r['id'] for r in rows]==list(range(557)) and len({r['path'] for r in rows})==557,'BOOTSTRAP_IMAGE_ORDER')
    need(any(r.get('kind')=='PRIVATE_SEALED' and r['path']==interpreter and r['sha256']==interpreter_sha256 for r in rows),'BOOTSTRAP_INTERPRETER_BINDING')
    return {'scope':BOOTSTRAP,'payload_sha256':payload_sha256,'interpreter':interpreter,'interpreter_sha256':interpreter_sha256,'expected_count':557}


def build_policy(*,manifest,static,plan,os_reference,standalone,parents):
    """Deterministic compiler over independently admitted static evidence.

    plan names private roots for the exact imports and independently reviewed OS
    candidates. All transitive private dependency edges come from static Mach-O
    load commands. OS candidates must exist in the signed cache catalogue or an
    independently reviewed Apple-signature record. Candidate cardinality is an
    upper bound, not a requirement to load every permissible OS image.
    """
    need(type(parents) is dict and set(parents)=={'manifest','static','plan','os_reference','standalone'},'PRODUCTION_POLICY_PARENTS')
    for name,value in locals().copy().items():
        if name in parents:need(digest(value)==parents[name],'PRODUCTION_POLICY_PARENT_HASH')
    need(static.get('status')=='PASS_STATIC_FINAL_LOCATION_ONLY' and static.get('runtime_executed') is False,'STATIC_RECEIPT_SCOPE')
    root=path(manifest['runtime_root']);source=manifest['release_commit']
    from provider_gateway_contract import canonical as runtime_canonical
    need(sha(runtime_canonical(manifest))==static['manifest_sha256'],'STATIC_MANIFEST_PARENT')
    need(static['source_commit']==source==plan['source_commit'],'PRODUCTION_SOURCE_PARENT')
    need(plan.get('scope')=='PRODUCTION_IMPORT_PLAN_V1' and plan['runtime_root']==root,'PRODUCTION_IMPORT_PLAN_SCOPE')
    need(type(plan.get('review_parent')) is str and HEX.fullmatch(plan['review_parent']),'PRODUCTION_IMPORT_PLAN_REVIEW')
    imports=plan['imports'];need(type(imports) is list and imports and len(imports)==len(set(imports)),'PRODUCTION_IMPORT_PLAN')
    for name in imports:need(type(name) is str and IMPORT.fullmatch(name) and not forbidden(name),'PRODUCTION_FORBIDDEN_IMPORT')
    need(type(manifest['file_inventory']) is list and len(manifest['file_inventory'])<=65536,'MANIFEST_FILE_COUNT')
    files={r['path']:r for r in manifest['file_inventory']}
    need(len(files)==len(manifest['file_inventory']),'MANIFEST_DUPLICATE_PATH')
    for name,row in files.items():
        path(name,False);hash_value(row['sha256']);need(type(row['size']) is int and row['size']>=0,'MANIFEST_FILE_SIZE')
    images={r['path']:r for r in static['images']};need(len(images)==len(static['images']),'STATIC_DUPLICATE_IMAGE')
    need(set(plan['import_images'])==set(imports),'IMPORT_IMAGE_COVERAGE')
    roots=[plan['interpreter']]+[p for name in imports for p in plan['import_images'][name]]
    need(len(roots)>=1 and all(p in images for p in roots),'APPROVED_PRIVATE_IMAGE_ROOTS')
    need(manifest['interpreter']==root+'/'+plan['interpreter'] and manifest['interpreter_sha256']==files[plan['interpreter']]['sha256'],'PRODUCTION_INTERPRETER_BINDING')
    os_paths=plan['os_image_paths'];need(type(os_paths) is list and len(os_paths)==len(set(os_paths)),'OS_UNIVERSE_DUPLICATE')
    need(os_reference.get('schema')=='SIGNED_OS_CACHE_REFERENCE_V1','SIGNED_OS_SCOPE')
    need(os_reference['source_build']==plan['host']['build'] and os_reference['arch']==plan['host']['arch'],'OS_HOST_BINDING')
    uuid_value(os_reference['cache_uuid'])
    signed=os_reference['signed_files'];need(signed and len({r['path'] for r in signed})==len(signed),'CACHE_FILE_SET')
    for row in signed:
        path(row['path']);hash_value(row['sha256']);need(row['apple_anchor_verified'] is True and row['exit']==0,'CACHE_APPLE_SIGNATURE')
    independent={r['path']:r for r in standalone};need(len(independent)==len(standalone),'STANDALONE_DUPLICATE')
    os_rows={}
    for name in sorted(os_paths):
        path(name);need(name.startswith(('/usr/lib/','/System/Library/')),'OS_IMAGE_ORIGIN')
        if name in os_reference['image_uuids']:
            identity=os_reference['image_uuids'][name];uuid_value(identity)
            os_rows[name]={'path':name,'uuid':identity,'kind':'APPLE_SIGNED_CACHE','reference_parent':parents['os_reference']}
        else:
            need(name in independent,'OS_IMAGE_INDEPENDENT_REFERENCE')
            r=independent[name];uuid_value(r['uuid']);hash_value(r['sha256']);hash_value(r['review_parent']);hash_value(r['signature_parent'])
            need(r['apple_anchor_verified'] is True and r['exit']==0 and type(r['size']) is int and r['size']>0,'STANDALONE_APPLE_SIGNATURE')
            os_rows[name]={k:r[k] for k in ('path','uuid','sha256','size','signature_parent','review_parent')};os_rows[name]['kind']='APPLE_SIGNED_STANDALONE'
    visited=set();pending=list(roots);required_os=set();private={}
    while pending:
        name=pending.pop()
        if name in visited:continue
        visited.add(name);path(name,False);need(name in files and name in images,'PRIVATE_DEPENDENCY_MANIFEST')
        image=images[name];file=files[name];need(image['sha256']==file['sha256'] and image['signature']=='VERIFIED','PRIVATE_IMAGE_STATIC_IDENTITY')
        uuid_value(image['uuid'])
        private[root+'/'+name]={'path':root+'/'+name,'kind':'PRIVATE_SEALED','file':name,'sha256':file['sha256'],'size':file['size'],'uuid':image['uuid']}
        for command,value in image['load_dependencies']:
            need(not forbidden(value),'PRODUCTION_FORBIDDEN_DEPENDENCY')
            if command=='LC_ID_DYLIB':continue
            need(command in LOADS,'DEPENDENCY_COMMAND')
            if value.startswith('@loader_path/'):
                target=posixpath.normpath(posixpath.join(posixpath.dirname(name),value[len('@loader_path/'):]))
                path(target,False);pending.append(target)
            elif value.startswith('@executable_path/'):
                target=posixpath.normpath(posixpath.join(posixpath.dirname(plan['interpreter']),value[len('@executable_path/'):]))
                path(target,False);pending.append(target)
            else:
                path(value);need(value in os_rows,'STATIC_DEPENDENCY_OUTSIDE_UNIVERSE');required_os.add(value)
    universe={**private,**os_rows};need(len(universe)==len(private)+len(os_rows) and 0<len(universe)<=MAX_IMAGES,'PRODUCTION_IMAGE_BOUND')
    rows=[dict(universe[name],id=i) for i,name in enumerate(sorted(universe))]
    mandatory=sorted(set(private)|required_os)
    return {'scope':PRODUCTION,'version':1,'source_commit':source,'runtime_root':root,'host':plan['host'],
            'parents':parents,'imports':imports,'interpreter':root+'/'+plan['interpreter'],'rows':rows,
            'required_paths':mandatory,'image_maximum':len(rows),'minimum_count':len(mandatory),
            'cache_uuid':os_reference['cache_uuid'],'module_files':sorted(files),
            'mapped_memory_integrity':'UNVERIFIED','boot_attestation':'UNRESOLVED',
            'runtime_executed':False,'report_maximum_bytes':MAX_REPORT_BYTES}


def verify_policy(policy,**inputs):
    need(policy.get('scope')==PRODUCTION,'PRODUCTION_REFERENCE_SCOPE')
    need(policy==build_policy(**inputs),'PRODUCTION_REFERENCE_RECONSTRUCTION')
    return policy


def verify_scans(policy,*,policy_parent,imports,scans,origins,cache_uuids):
    """No observation can modify the independently constructed allowed universe."""
    need(policy.get('scope')==PRODUCTION,'PRODUCTION_REFERENCE_SCOPE')
    need(digest(policy)==policy_parent,'PRODUCTION_REFERENCE_HASH')
    need(imports==policy['imports'],'RUNTIME_IMPORT_PLAN_EXACT')
    need(type(scans) is list and len(scans)==2,'TWO_COMPLETE_IMAGE_SCANS')
    need(type(origins) is list and all(type(r) is dict and set(r)=={'module','file'} for r in origins),'MODULE_ORIGIN_SCHEMA')
    need(len({r['module'] for r in origins})==len(origins),'DUPLICATE_MODULE_ORIGIN')
    for row in origins:
        need(not forbidden(row['module']) and not forbidden(row['file']),'PRODUCTION_FORBIDDEN_MODULE')
        need(row['file'] in policy['module_files'],'MODULE_ORIGIN_OUTSIDE_SEAL')
    need(cache_uuids==[policy['cache_uuid']]*2,'RUNTIME_CACHE_UUID')
    allowed={r['path']:r for r in policy['rows']}
    need(len(allowed)==len(policy['rows'])==policy['image_maximum'],'REFERENCE_IMAGE_COUNT')
    for scan in scans:
        need(type(scan) is dict and set(scan)=={'complete','count','images'},'IMAGE_SCAN_SCHEMA')
        rows=scan['images'];need(scan['complete'] is True,'IMAGE_SCAN_INCOMPLETE')
        need(type(rows) is list and type(scan['count']) is int and scan['count']==len(rows),'IMAGE_SCAN_COUNT')
        need(policy['minimum_count']<=len(rows)<=policy['image_maximum'],'IMAGE_REPORT_OVERFLOW_OR_MISSING')
        seen=set()
        for row in rows:
            need(type(row) is dict and set(row)=={'path','uuid'},'OBSERVED_IMAGE_SCHEMA')
            name=path(row['path']);uuid_value(row['uuid']);need(name not in seen,'DUPLICATE_LOADED_IMAGE');seen.add(name)
            need(name in allowed,'IMAGE_OUTSIDE_UNIVERSE');need(row['uuid']==allowed[name]['uuid'],'LOADED_IMAGE_UUID')
        need(set(policy['required_paths'])<=seen,'REQUIRED_LOADED_IMAGE_MISSING')
    need(scans[0]==scans[1],'IMAGE_SCAN_STABILITY')
    return {'scope':PRODUCTION,'policy_parent':policy_parent,'imports_exact':True,'scans':2,'images':scans[0]['count'],
            'image_maximum':policy['image_maximum'],'mapped_memory_integrity':'UNVERIFIED','boot_attestation':'UNRESOLVED'}


def decode_report(raw,policy,parent):
    need(type(raw) is bytes and 0<len(raw)<=policy['report_maximum_bytes']<=MAX_REPORT_BYTES,'RUNTIME_REPORT_OVERFLOW')
    def unique(pairs):
        result={}
        for key,value in pairs:need(key not in result,'RUNTIME_REPORT_DUPLICATE_KEY');result[key]=value
        return result
    report=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:need(False,'RUNTIME_REPORT_NONFINITE'))
    need(type(report) is dict and set(report)=={'scope','policy_parent','imports','scans','origins','cache_uuids'},'RUNTIME_REPORT_SCHEMA')
    need(report.pop('scope')==PRODUCTION and report.pop('policy_parent')==parent,'RUNTIME_REPORT_SCOPE_PARENT')
    return verify_scans(policy,policy_parent=parent,**report)


def bound_json(binding):
    pin_file(binding['path'],binding['sha256']);raw=Path(binding['path']).read_bytes()
    need(sha(raw)==binding['sha256'],'REFERENCE_INPUT_MUTATION');return json.loads(raw)


def run_stage(context,row,deadline,budget):
    """Write external policy only after the exact durable static GREEN receipt."""
    parent=context.require_completed(STAGES[5]);context.check('REFERENCE_STAGE_DEADLINE')
    d=context.manifest['native']['production_reference'];inputs={k:bound_json(d[k]) for k in ('plan','os_reference','standalone')}
    assembly=context.require_completed(STAGES[4])
    result_path=Path(assembly['detail']['execution'])/'ASSEMBLY-RESULT.json'
    result=json.loads(result_path.read_bytes());inputs['manifest']=result['manifest']
    inputs['static']=parent['detail']['static']
    for binding in inputs['os_reference']['signed_files']+inputs['standalone']:
        context.check('REFERENCE_OS_REVALIDATION_DEADLINE');pin_file(binding['path'],binding['sha256'])
    context.check('REFERENCE_OS_REVALIDATION_DEADLINE')
    need(inputs['manifest']['release_commit']==context.manifest['source']['commit'],'REFERENCE_SOURCE')
    need(inputs['manifest']['runtime_root']==str(context.root/'payload/assembly-output/execution-01/output/runtime-pilot'),'REFERENCE_FINAL_ROOT')
    # The static receipt supplies independently extracted UUIDs and dependency edges.
    inputs['parents']={k:digest(v) for k,v in inputs.items()}
    policy=build_policy(**inputs);verify_policy(policy,**inputs);context.check('REFERENCE_STAGE_DEADLINE')
    destination=context.root/'PRODUCTION-RUNTIME-IMAGE-POLICY.json'
    need(not destination.is_relative_to(Path(policy['runtime_root'])),'REFERENCE_EXTERNAL_TO_RUNTIME')
    raw=canonical(policy);fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    pin_file(destination,sha(raw));context.check('REFERENCE_STAGE_DEADLINE')
    return context.receipt(row,artifacts=[{'path':str(destination),'sha256':sha(raw)}],extra={'policy_parent':digest(policy),
        'policy_path':str(destination),'static_receipt_parent':digest(parent),'image_maximum':policy['image_maximum'],
        'scope':PRODUCTION,'runtime_executed':False})
