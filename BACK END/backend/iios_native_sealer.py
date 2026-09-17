"""Prepared bottom-up derived-code seal controller; importing has no effects."""
import hashlib,json,os,stat,time,subprocess,select,re
from pathlib import Path
from iios_native_seal_protocol import SEAL_FILES,DERIVED_CODE,verify_seal_delta,read_owned_json
from iios_native_conductor import require,STAGES
R=None
tool=None
inspect_macos=None
def need(value,predicate):require(value,STAGES[4],predicate)
sha=lambda b:hashlib.sha256(b).hexdigest()
from truth_spine_contract import canonical

def publish(name,v):
    p=R/'assembly-output/execution-01'/name
    with p.open('xb') as f:f.write(canonical(v));f.flush();os.fsync(f.fileno())
    p.chmod(0o400);return sha(canonical(v))

def signature_identity(binary,deadline,pins):
    result={}
    for arch in ('arm64','x86_64'):
        rc,out,err=tool(['/usr/bin/codesign','-d','--verbose=4','--arch',arch,str(binary)],deadline,pins)
        need(rc==0,'SIGNATURE_DISPLAY');text=(out+err).decode('utf-8');fields={}
        for key,pattern in {'identifier':r'^Identifier=(.+)$','flags':r'^CodeDirectory .* flags=([^ ]+) ',
                            'runtime':r'^Runtime Version=(.+)$','team':r'^TeamIdentifier=(.+)$','kind':r'^Signature=(.+)$'}.items():
            m=re.search(pattern,text,re.M);need(m is not None,'SIGNATURE_FIELD');fields[key]=m[1]
        need(re.fullmatch(r'0x[0-9a-f]+\([a-z,]+\)',fields['flags']) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',fields['runtime']),'SIGNATURE_FIELD_FORMAT')
        need(fields['identifier']=='org.python.python' and fields['kind']=='adhoc' and fields['team']=='not set','SIGNATURE_IDENTITY')
        rc,out,err=tool(['/usr/bin/codesign','-d','--entitlements',':-','--arch',arch,str(binary)],deadline,pins);need(rc==0,'SIGNATURE_ENTITLEMENTS');fields['entitlements_sha256']=sha(out)
        rc,out,err=tool(['/usr/bin/codesign','-d','--requirements',':-','--arch',arch,str(binary)],deadline,pins);need(rc==0,'SIGNATURE_REQUIREMENTS');fields['requirements_sha256']=sha(out)
        result[arch]=fields
    return result

def image_identity(path,relative,kind,signature,deadline,pins,expected,expected_sha256):
    from alpha_assembly_file_type import inspect_file_type
    inspect_file_type(tool,path,relative,kind,deadline,pins,expected_sha256)
    rc,out,err=tool(['/usr/bin/lipo','-archs',str(path)],deadline,pins);need(rc==0 and out.decode().split()==['x86_64','arm64'],'DERIVED_ARCHITECTURES')
    rc,out,err=tool(['/Library/Developer/CommandLineTools/usr/bin/llvm-otool','-l',str(path)],deadline,pins);need(rc==0,'DERIVED_LOAD_COMMANDS')
    text=out.decode();names=[]
    for block in text.split('Load command '):
        command=re.search(r'\n\s*cmd (LC_\w+)',block);value=re.search(r'\n\s*name (.*?) \(offset ',block)
        if command and value:names.append((command[1],value[1]))
    install=sorted({value for command,value in names if command=='LC_ID_DYLIB'})
    dependencies=sorted({value for command,value in names if command in ('LC_LOAD_DYLIB','LC_LOAD_WEAK_DYLIB','LC_REEXPORT_DYLIB','LC_LOAD_UPWARD_DYLIB')})
    need(install==expected['install_names'] and dependencies==expected['dependencies'],'DERIVED_DEPENDENCIES')
    rc,out,err=tool(['/usr/bin/codesign','--verify','--strict','--all-architectures',str(path)],deadline,pins)
    if signature=='STRICT_VERIFICATION_FAILED_UNSIGNED':
        need(rc==1 and err.rstrip().endswith(b'code object is not signed at all'),'DERIVED_PRE_SIGNATURE')
    else:need(rc==0,'DERIVED_POST_SIGNATURE')
    return {'path':relative,'size':path.stat().st_size,'sha256':sha(path.read_bytes()),'file_type':kind,
            'architectures':['x86_64','arm64'],'load_commands_sha256':sha(out if False else tool(['/Library/Developer/CommandLineTools/usr/bin/llvm-otool','-l',str(path)],deadline,pins)[1]),
            'install_names':install,'dependencies':dependencies,'signature':signature}

class Sealer:
    def __init__(self,descriptor):self.d=descriptor;self.done=False
    def __call__(self,child,registered,deadline):
        if self.done or not (R/'assembly-output/execution-01/STAGING-RESULT.json').exists():return
        need(registered is not None and child.poll() is None,'SEAL_CHILD_OWNERSHIP')
        fresh=inspect_macos(child.pid);need(fresh==registered,'SEAL_CHILD_IDENTITY')
        stage,raw=read_owned_json(R/'assembly-output/execution-01/STAGING-RESULT.json',8_000_000)
        need(raw==canonical(stage) and stage['source_commit']==self.d['source'] and stage['plan_parent']==self.d['plan_parent'] and stage['budget_parent']==self.d['budget_parent'],'STAGING_PARENT')
        from alpha_runtime_files import verify_runtime_tree,inventory_runtime,validate_production_signing_evidence,production_layout_policy
        from provider_gateway_contract import content_hash
        root=R/'assembly-output/execution-01/staging';observed=stage['observed'];plan=json.loads((R/'ASSEMBLY-PLAN-v3.json').read_bytes())
        verify_runtime_tree(str(root),observed['files'],approved_root=str(root),layout_policy=plan['layout_policy'],layout_parent=plan['layout_parent'],metadata=observed['metadata'])
        policy=production_layout_policy();need(policy==plan['layout_policy'] and DERIVED_CODE==tuple(x['path'] for x in policy['required_derived_code']),'SEAL_POLICY')
        requirements={x['path']:x for x in policy['required_derived_code']}
        before_runtime=signature_identity(root/'Python',deadline,self.d['tool_pins'])
        pre=[image_identity(root/name,name,requirements[name]['file_type'],'STRICT_VERIFICATION_FAILED_UNSIGNED',deadline,self.d['tool_pins'],requirements[name],self.d['previously_unsigned_wheel_images'][name]) for name in DERIVED_CODE]
        originals={r['path']:r for r in observed['files'] if r['path'] in SEAL_FILES};need(set(originals)==SEAL_FILES,'SEAL_FILE_SET')
        for path in (root,root/'_CodeSignature'):path.chmod(0o700)
        for name in SEAL_FILES:(root/name).chmod(0o600)
        commands=[]
        try:
            for name in DERIVED_CODE:
                argv=['/usr/bin/codesign','--force','--sign','-','--timestamp=none',str(root/name)]
                rc,out,err=tool(argv,deadline,self.d['tool_pins']);need(rc==0,'DERIVED_SIGN_FAILED')
                commands.append(['/usr/bin/codesign','--force','--sign','-','--timestamp=none',name])
            rc,out,err=tool(['/usr/bin/codesign','--force','--sign','-','--preserve-metadata=identifier,requirements,entitlements,flags,runtime','--timestamp=none',str(root/'Python')],deadline,self.d['tool_pins']);need(rc==0,'RESOURCE_SEAL_FAILED')
        finally:
            for name in SEAL_FILES:(root/name).chmod(originals[name]['mode'])
            for path in (root/'_CodeSignature',root):path.chmod(0o500)
        post=[image_identity(root/name,name,requirements[name]['file_type'],'IIOS_ADHOC_DERIVED_VERIFIED',deadline,self.d['tool_pins'],requirements[name],sha((root/name).read_bytes())) for name in DERIVED_CODE]
        after_runtime=signature_identity(root/'Python',deadline,self.d['tool_pins']);need(before_runtime==after_runtime,'SIGNATURE_POLICY_CHANGED')
        rc,out,err=tool(['/usr/bin/codesign','--verify','--deep','--strict','--all-architectures',str(root/'Python')],deadline,self.d['tool_pins']);need(rc==0,'RESOURCE_SEAL_VERIFY')
        evidence={'schema':'iios-production-signing-evidence-v1','policy_parent':content_hash(policy),'pre_transform':pre,'post_sign':post,
            'signing_order':list(DERIVED_CODE)+['Python'],'sign_commands':commands,
            'final_verification':['/usr/bin/codesign','--verify','--deep','--strict','--all-architectures','Python'],
            'enclosing_runtime':{'path':'Python','signed_after':list(DERIVED_CODE),'signature':'IIOS_ADHOC_RESOURCE_SEAL_VERIFIED'}}
        evidence_parent=content_hash(evidence);validate_production_signing_evidence(evidence,evidence_parent)
        derived={n:dict(path=n,size=(root/n).stat().st_size,mode=stat.S_IMODE((root/n).stat().st_mode),sha256=sha((root/n).read_bytes())) for n in SEAL_FILES}
        receipt=dict(schema='iios-resource-seal-receipt-v2',status='PASS_BOTTOM_UP_RESOURCE_SEAL_ONLY',source_commit=self.d['source'],staging_parent=sha(raw),budget_parent=self.d['budget_parent'],seal_kind='IIOS_BOTTOM_UP_ADHOC_RESOURCE_SEAL',original_files=originals,derived_files=derived,signature_identity=after_runtime,signing_evidence=evidence,signing_evidence_parent=evidence_parent,vendor_signature_receipt_sha256=self.d['vendor_signature_receipt_sha256'],host_contract=self.d['host_contract'],production_qualified=False,provider_access=False,credential_access=False,broker_connected=False,paper_order_permission=False,trade_execution_permission=False,live_execution=False)
        post_inventory=inventory_runtime(str(root),plan['layout_policy'],plan['layout_parent'],approved_root=str(root));verify_seal_delta(observed,post_inventory,receipt)
        need(inspect_macos(child.pid)==registered and child.poll() is None,'SEAL_CHILD_IDENTITY')
        parent=publish('RESOURCE-SEAL-RECEIPT.json',receipt);publish('RESOURCE-SEAL-ACK.json',dict(receipt_sha256=parent,receipt_size=len(canonical(receipt)),staging_parent=sha(raw),budget_parent=self.d['budget_parent']))
        self.done=True

def configure(context):
    global R,tool,inspect_macos
    R=context.root/'payload';tool=context.tool;inspect_macos=context.inspect
