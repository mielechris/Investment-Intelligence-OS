"""Production adapter generated from the pinned accepted bootstrap child contract.

The legacy file and 557-image payload are never edited. Only a separately pinned
production child is emitted, with a production policy and projected import plan.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
from iios_native_conductor import STAGES,require,digest,canonical,pin_file
from iios_native_image_policy import PRODUCTION,decode_report,sha,bound_json

STAGE=STAGES[7]

# Same accepted dyld APIs and UUID observations. The independent policy supplies
# a finite bound; no initial observation is copied into an allow-list.
COLLECT='''
def collect_inventory(ctypes,time_module,work,gate,origins,ca_hash,ca_count):
    lib=ctypes.CDLL(None)
    count=lib._dyld_image_count;count.argtypes=[];count.restype=ctypes.c_uint32
    name=lib._dyld_get_image_name;name.argtypes=[ctypes.c_uint32];name.restype=ctypes.c_char_p
    header=lib._dyld_get_image_header;header.argtypes=[ctypes.c_uint32];header.restype=ctypes.c_void_p
    uuid_query=lib._dyld_get_image_uuid;uuid_query.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ubyte)];uuid_query.restype=ctypes.c_bool
    cache_query=lib._dyld_get_shared_cache_uuid;cache_query.argtypes=[ctypes.POINTER(ctypes.c_ubyte)];cache_query.restype=ctypes.c_bool
    def cache_uuid():
        buf=(ctypes.c_ubyte*16)();need(cache_query(buf) is True,'CACHE_UUID');return bytes(buf).hex()
    def sample():
        n=count();need(type(n) is int and 0<n<=IMAGE_MAXIMUM,'IMAGE_REPORT_OVERFLOW')
        rows=[];addresses=[]
        for i in range(n):
            need(clock_ns(time_module)<work,'DIAGNOSTIC_DEADLINE')
            raw=name(i);need(type(raw) is bytes and 1<=len(raw)<=4096,'DIAGNOSTIC_NAME')
            path=raw.decode('utf-8','strict');need(safe_path(path),'DIAGNOSTIC_PATH')
            address=header(i);need(type(address) is int and 0<address<2**64,'DIAGNOSTIC_HEADER')
            buf=(ctypes.c_ubyte*16)();need(uuid_query(address,buf) is True,'IMAGE_UUID')
            need(address not in addresses,'IMAGE_DUPLICATE');addresses.append(address)
            rows.append({'path':path,'uuid':bytes(buf).hex()})
        need(count()==n,'IMAGE_COUNT_STABILITY')
        return {'complete':True,'count':n,'images':rows},tuple(addresses)
    before=cache_uuid();first,addresses_first=sample();second,addresses_second=sample();after=cache_uuid()
    need(first==second and addresses_first==addresses_second and before==after==EXPECTED_CACHE_UUID,'IMAGE_SCAN_STABILITY')
    rows=[{'module':name,'file':MODULE_FILES[index]} for name,index in origins if index>=0]
    return json.dumps({'scope':'PRODUCTION_RUNTIME_IMAGE_POLICY_V1','policy_parent':IMAGE_REFERENCE_PARENT,
        'imports':list(APPROVED_IMPORTS),'scans':[first,second],'origins':rows,'cache_uuids':[before,after]},sort_keys=True,separators=(',',':')).encode()
'''


def generate_child(template,policy,*,destination,discovery):
    require(policy['scope']==PRODUCTION,STAGE,'PRODUCTION_CHILD_SCOPE')
    tree=ast.parse(template);original_imports=None
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APPROVED_IMPORTS' for t in node.targets):original_imports=ast.literal_eval(node.value)
    require(original_imports is not None and policy['imports']==[n for n in original_imports if n!='_tkinter'],STAGE,'PRODUCTION_CHILD_IMPORT_PLAN')
    constants={'ROOT':policy['runtime_root'],'PREP':str(Path(destination).parent),
               'CA':policy['runtime_root']+'/lib/python3.14/site-packages/certifi/cacert.pem',
               'APPROVED_IMPORTS':tuple(policy['imports']),'REQUIRED_IMPORTS':tuple(policy['imports']),
               'MODULE_FILES':tuple(policy['module_files']),'IMAGE_MAXIMUM':policy['image_maximum'],
               'IMAGE_REFERENCE_PARENT':digest(policy),'EXPECTED_CACHE_UUID':policy['cache_uuid'],
               'SCOPE':PRODUCTION,'SEALED_IMPORT_NAMES':tuple(discovery),'IMAGE_PATHS':tuple(r['path'] for r in policy['rows']),
               'IMAGE_UUIDS':tuple(r['uuid'] for r in policy['rows'])}
    changed=set()
    class Transform(ast.NodeTransformer):
        def visit_Assign(self,node):
            if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='CODES':
                node.value=ast.parse(repr(tuple(ast.literal_eval(node.value))+('IMAGE_REPORT_OVERFLOW','IMAGE_SCAN_STABILITY','IMAGE_COUNT_STABILITY')),mode='eval').body
            if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in constants:
                name=node.targets[0].id;node.value=ast.parse(repr(constants[name]),mode='eval').body;changed.add(name)
            if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='import_one' and node.value.args and isinstance(node.value.args[0],ast.Constant) and node.value.args[0].value=='_tkinter':return None
            return self.generic_visit(node)
        def visit_FunctionDef(self,node):
            if node.name=='collect_inventory':return ast.parse(COLLECT).body[0]
            if node.name in ('encode_acceptance','decode_acceptance','validate_origins'):return None
            if node.name=='failure_detail':
                for item in ast.walk(node):
                    if isinstance(item,ast.Return) and isinstance(item.value,ast.Dict):
                        item.value.keys.extend([ast.Constant('exception_subtype'),ast.Constant('errno_category')])
                        item.value.values.extend([ast.parse('type(error).__name__',mode='eval').body,
                            ast.parse("{1:'EPERM',13:'EACCES',2:'ENOENT',3:'ESRCH',5:'EIO'}.get(getattr(error,'errno',None),'NONE_OR_OTHER')",mode='eval').body])
            return self.generic_visit(node)
    tree=Transform().visit(tree);ast.fix_missing_locations(tree)
    require(set(constants)<=changed,STAGE,'PRODUCTION_CHILD_TEMPLATE_BINDINGS')
    text=ast.unparse(tree)
    # Preserve accepted TLS checks and all startup/ACK/identity/audit predicates.
    text=text.replace("PREP + '/diagnostic_child.py'",repr(str(destination)))
    text=text.replace('> 32768','> 4194304')
    result=ast.parse(text)
    calls=[n.args[0].value for n in ast.walk(next(n for n in result.body if isinstance(n,ast.FunctionDef) and n.name=='main'))
           if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='import_one' and n.args and isinstance(n.args[0],ast.Constant)]
    require(calls==policy['imports'],STAGE,'PRODUCTION_CHILD_IMPORT_ORDER')
    require(not any(isinstance(n,ast.Constant) and n.value=='_tkinter' for n in ast.walk(result)),STAGE,'PRODUCTION_CHILD_FORBIDDEN_IMPORT')
    return (text+'\n').encode()


def decode_acceptance(raw,policy):
    require(type(raw) is bytes and len(raw)<=policy['report_maximum_bytes'],STAGE,'RUNTIME_REPORT_OVERFLOW')
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result,STAGE,'RUNTIME_REPORT_DUPLICATE_KEY');result[key]=value
        return result
    value=json.loads(raw,object_pairs_hook=unique)
    expected={'scope','policy_parent','imports','scans','origins','cache_uuids','stage','ca_sha256','ca_count','tls_context_only'}
    require(set(value)==expected,STAGE,'RUNTIME_ACCEPTANCE_COMPLETE_REPORT')
    require(value.pop('stage')=='COMPLETE' and value.pop('tls_context_only') is True,STAGE,'RUNTIME_TLS_CONTEXT')
    require(value.pop('ca_sha256')=='9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f' and value.pop('ca_count')==121,STAGE,'RUNTIME_CA_BINDING')
    return decode_report(canonical(value),policy,digest(policy))


def run_stage(context,row,deadline,budget):
    parent=context.require_completed(STAGES[6]);static=context.require_completed(STAGES[5])
    detail=parent['detail'];require(detail['scope']==PRODUCTION and detail['static_receipt_parent']==digest(static),STAGE,'RUNTIME_REFERENCE_RECEIPT_PARENT')
    path=detail['policy_path'];require(path==str(context.root/'PRODUCTION-RUNTIME-IMAGE-POLICY.json'),STAGE,'RUNTIME_REFERENCE_EXTERNAL_PATH')
    policy=json.loads(Path(path).read_bytes());require(digest(policy)==detail['policy_parent'],STAGE,'RUNTIME_REFERENCE_RECEIPT_HASH')
    d=context.manifest['native']['runtime_acceptance']
    pin_file(d['template']['path'],d['template']['sha256']);template=Path(d['template']['path']).read_bytes()
    require(sha(template)==d['template']['sha256'],STAGE,'RUNTIME_TEMPLATE_MUTATION')
    # Reuse the admitted inventory-to-discovery function, never filesystem discovery.
    from iios_native_discovery import regenerate
    assembly=context.require_completed(STAGES[4]);result=json.loads((Path(assembly['detail']['execution'])/'ASSEMBLY-RESULT.json').read_bytes())
    manifest=result['manifest']
    from alpha_runtime_files import verify_manifest
    verify_manifest(policy['runtime_root'],manifest,source_commit=context.manifest['source']['commit'])
    destination=context.root/'production-runtime-child.py'
    raw=generate_child(template,policy,destination=destination,discovery=regenerate({'files':manifest['file_inventory']}))
    with destination.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    startup=min(deadline,context.clock()+60_000_000_000)
    execution=context.run_owned_runtime(destination,sha(raw),policy,startup,deadline)
    verified=decode_acceptance(execution['report'],policy)
    verify_manifest(policy['runtime_root'],manifest,source_commit=context.manifest['source']['commit'])
    require(execution['cleanup']['verified'] is True and execution['cleanup']['signals']==0,STAGE,'RUNTIME_VERIFIED_CLEANUP')
    return context.receipt(row,artifacts=[{'path':str(destination),'sha256':sha(raw)}],extra={'identity':verified,
        'reference_receipt_parent':digest(parent),'ownership':execution['ownership'],'cleanup':execution['cleanup'],
        'runtime_executed':True,'scope':PRODUCTION})
