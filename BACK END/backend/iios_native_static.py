"""Read-only final-location verification; never executes the final interpreter."""
import json,hashlib,re,posixpath,time
from pathlib import Path
from iios_native_conductor import require, STAGES
from iios_native_seal_binding import image_parent
def need(value,predicate):require(value,STAGES[5],predicate)
sha=lambda b:hashlib.sha256(b).hexdigest()
def verify(d,deadline,*,execution,tool,clock):
    execution=Path(execution)
    from alpha_runtime_files import verify_manifest,verify_runtime_tree,extension
    result=json.loads((execution/'ASSEMBLY-RESULT.json').read_bytes());m=result['manifest'];root=Path(m['runtime_root'])
    need(str(root)==str(execution/'output/runtime-pilot'),'FINAL_ROOT')
    verify_manifest(str(root),m,source_commit=d['source']);files={r['path']:r for r in m['file_inventory']}
    baseline=[row for row in json.loads(Path(d['load_baseline']['path']).read_bytes())['files']
              if row['path'] in files]
    wheels=json.loads(Path(d['wheel_macho']['path']).read_bytes())['images']
    rows=baseline+[dict(path='lib/python3.14/site-packages/'+x['member'],sha256=x['sha256'],load_dependencies=x['load_commands']) for x in wheels]
    receipt=json.loads((execution/'RESOURCE-SEAL-RECEIPT.json').read_bytes())
    from alpha_runtime_files import validate_production_signing_evidence
    from provider_gateway_contract import content_hash
    need(receipt['schema']=='iios-resource-seal-receipt-v2' and receipt['signing_evidence_parent']==content_hash(receipt['signing_evidence']),'FINAL_SIGNING_RECEIPT')
    reports=[]
    rc,_,_=tool(['/usr/bin/codesign','--verify','--deep','--strict','--all-architectures',str(root/'Python')],deadline,d['tool_pins']);need(rc==0,'FINAL_RESOURCE_SEAL')
    for row in rows:
        need(clock()<deadline,'FINAL_STATIC_DEADLINE');name=row['path'];p=root/name
        need(not p.is_symlink() and sha(p.read_bytes())==files[name]['sha256'],'FINAL_IMAGE_HASH')
        image_parent(name,row['sha256'],files[name]['sha256'],receipt,validate_signing=validate_production_signing_evidence)
        rc,out,err=tool(['/Library/Developer/CommandLineTools/usr/bin/llvm-otool','-l',str(p)],deadline,d['tool_pins']);need(rc==0,'FINAL_LOAD_QUERY')
        text=out.decode();need('LC_RPATH' not in text and 'LC_DYLD_ENVIRONMENT' not in text,'FINAL_LOAD_ENVIRONMENT');names=[]
        for block in text.split('Load command '):
            kind=re.search(r'\n\s*cmd (LC_\w+)',block);value=re.search(r'\n\s*name (.*?) \(offset ',block)
            if kind and value:names.append([kind[1],value[1]])
        need(names==row['load_dependencies'],'FINAL_LOAD_MUTATION')
        for kind,value in names:
            if kind=='LC_ID_DYLIB':continue
            if value.startswith('@loader_path/'):
                target=posixpath.normpath(posixpath.join(posixpath.dirname(name),value[len('@loader_path/'):]))
                need(target in files and not (root/target).is_symlink() and sha((root/target).read_bytes())==files[target]['sha256'],'FINAL_DEPENDENCY')
            else:need(value.startswith(('/usr/lib/','/System/Library/')),'FINAL_DEPENDENCY_LOCATION')
        rc,out,err=tool(['/usr/bin/codesign','--verify','--strict','--all-architectures',str(p)],deadline,d['tool_pins'])
        need(rc==0,'FINAL_IMAGE_SIGNATURE')
        from iios_native_macho import image_uuid
        raw=p.read_bytes();need(sha(raw)==files[name]['sha256'],'FINAL_IMAGE_UUID_BYTES')
        reports.append(dict(path=name,sha256=files[name]['sha256'],uuid=image_uuid(raw),load_dependencies=names,signature='VERIFIED'))
    receipt=json.loads((execution/'RESOURCE-SEAL-RECEIPT.json').read_bytes())
    from alpha_runtime_files import validate_production_signing_evidence
    from provider_gateway_contract import content_hash
    need(receipt['schema']=='iios-resource-seal-receipt-v2' and
         receipt['signing_evidence_parent']==content_hash(receipt['signing_evidence']),'FINAL_SIGNING_RECEIPT')
    validate_production_signing_evidence(receipt['signing_evidence'],receipt['signing_evidence_parent'])
    boot=json.loads(Path(d['bootstrap_inventory']['path']).read_bytes());rootboot=d['bootstrap_root']
    verify_runtime_tree(rootboot,boot['files'],approved_root=rootboot,**extension(boot))
    rc,_,_=tool(['/usr/bin/codesign','--verify','--deep','--strict','--all-architectures',rootboot+'/Python'],deadline,d['tool_pins']);need(rc==0,'BOOTSTRAP_SIGNATURE_CHANGED')
    verify_manifest(str(root),m,source_commit=d['source'])
    return dict(status='PASS_STATIC_FINAL_LOCATION_ONLY',source_commit=d['source'],images=reports,
        manifest_sha256=result['manifest_sha256'],envelope_sha256=result['envelope_sha256'],bootstrap_unchanged=True,
        runtime_executed=False,production_qualified=False,provider_access=False,credential_access=False,
        broker_connected=False,paper_order_permission=False,trade_execution_permission=False,live_execution=False)


def run_stage(context,row,deadline,budget):
    """Adapter invokes the migrated verifier only after durable assembly GREEN."""
    parent=context.require_completed(STAGES[4])
    from iios_native_conductor import digest
    require(parent['detail'].get('execution')==str(context.root/'payload/assembly-output/execution-01'),STAGES[5],'STATIC_ASSEMBLY_ROOT_PARENT')
    d=context.manifest['native']['static_descriptor']
    result=verify(d,deadline,execution=parent['detail']['execution'],tool=context.tool,clock=context.clock)
    require(result['status']=='PASS_STATIC_FINAL_LOCATION_ONLY',STAGES[5],'STATIC_RESULT')
    return context.receipt(row,extra={'static':result,'assembly_receipt_parent':digest(parent)})
