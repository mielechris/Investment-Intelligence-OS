"""Assemble a new read-only diagnostic from independently verified static inputs."""
import ast,hashlib,json,os,stat,subprocess,sys,time,datetime
from pathlib import Path
R=Path(sys.argv[1]).resolve()
P=Path(sys.argv[2]).resolve()
SOURCE=Path(sys.argv[3]).resolve();HEAD=sys.argv[4];CI=sys.argv[5]
sys.path.insert(0,str(SOURCE/'BACK END/backend'))
import alpha_runtime_files as rf
from iios_native_macho import image_uuid
from iios_native_discovery import regenerate
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
canonical=lambda v:json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def put(name,value):
 p=R/name
 with p.open('xb') as f:f.write(value if isinstance(value,bytes) else json.dumps(value,indent=2).encode()+b'\n')
 p.chmod(0o400);return p
seal=json.loads((P/'evidence/FINAL-SEALED-BOOTSTRAP-V2.json').read_bytes());B=Path(seal['runtime_root'])
rf.verify_runtime_tree(str(B),seal['files'],approved_root=str(B),layout_policy=seal['layout_policy'],layout_parent=seal['layout_parent'],metadata=seal['metadata'])
boot=subprocess.check_output(['/usr/sbin/sysctl','-n','kern.bootsessionuuid'],text=True,timeout=5).strip().lower();assert boot==seal['boot_session_uuid']
osref=json.loads((P/'evidence/host-current/OS-PROVENANCE.json').read_bytes());assert osref['boot_session_uuid']==boot
assert subprocess.check_output(['/usr/bin/sw_vers','-buildVersion'],text=True,timeout=5).strip()==osref['source_build']
ci=json.loads((R/'evidence'/('ci-'+CI)/'results.json').read_bytes());assert ci['head']==HEAD and ci['passed']
loads=json.loads((P/'evidence/FINAL-LOAD-AND-SIGNATURE-METADATA.json').read_bytes())['reports']
cache_set=put('CACHE-BACKING.json',{'cache_uuid':osref['cache_uuid'],'signed_files':osref['signed_files']})
catalog={}
for row in loads:
 path=B/row['path'];assert sha(path)==row['sha256']
 try:uuid=image_uuid(path.read_bytes())
 except ValueError:
  assert row['path'] in ('bin/python3-intel64','bin/python3.14-intel64');continue
 catalog[str(path)]={'uuid':uuid,'kind':'PRIVATE_SEALED','backing':{'path':str(path),'size':path.stat().st_size,'sha256':sha(path)}}
# Resolve only the statically admitted framework links; aliases are prospective candidates, never expected membership.
links={str(B/x['path']):x['target'] for x in seal['layout_policy']['links']}
for _ in range(3):
 for alias,target in links.items():
  canonical_target=str((Path(alias).parent/target).resolve())
  for path,row in list(catalog.items()):
   if path==canonical_target or path.startswith(canonical_target+'/'):
    candidate=alias+path[len(canonical_target):]
    if Path(candidate).is_file() and Path(candidate).resolve()==Path(row['backing']['path']):catalog[candidate]=row
for path,uuid in osref['image_uuids'].items():
 assert path not in catalog
 catalog[path]={'uuid':uuid,'kind':'APPLE_SIGNED_CACHE','backing':{'cache_uuid':osref['cache_uuid'],'cache_set_sha256':sha(cache_set)}}
stand=Path('/usr/lib/libffi-trampolines.dylib');assert str(stand) not in catalog
catalog[str(stand)]={'uuid':image_uuid(stand.read_bytes()),'kind':'APPLE_LIBFFI_TRAMPOLINE','backing':{'path':str(stand),'sha256':sha(stand),'size':stand.stat().st_size}}
catalog_file=put('INDEPENDENT-CANDIDATE-CATALOG.json',{'schema':'IIOS_DISCOVERY_CANDIDATES_V1','catalog':catalog,'cache_set_sha256':sha(cache_set),'purpose':'PROSPECTIVE_DISCOVERY_ONLY_NOT_ACCEPTED_MEMBERSHIP','measured_count':None,'historical_reference_recovered':False})
expires=int(time.time())+24*3600
source_py=SOURCE/'BACK END/backend/iios_bootstrap_diagnostic.py';source_c=SOURCE/'scripts/iios_bootstrap_diagnostic.c'
source_text=source_py.read_text();ast.parse(source_text)
descriptor={'schema':'IIOS_BOOTSTRAP_DIAGNOSTIC_ATTEMPT_V1','scope':'DISCOVERY_ONLY','source_commit':HEAD,'ci_run':CI,'boot_session_uuid':boot,'os_build':osref['source_build'],'bootstrap_root':str(B),'bootstrap_manifest_sha256':sha(P/'evidence/FINAL-SEALED-BOOTSTRAP-V2.json'),'catalog_sha256':sha(catalog_file),'python_source_sha256':sha(source_py),'supervisor_source_sha256':sha(source_c),'imports':list(__import__('iios_bootstrap_diagnostic').IMPORTS),'workload_cwd':str(R),'workload_environment':{'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC','OPENSSL_CONF':'/dev/null','__CF_USER_TEXT_ENCODING':'0x1F5:0x0:0x0'},'limits':{'total_seconds':900,'bootstrap_seconds':120,'child_self_alarm_seconds':122,'scan_seconds':90,'images':4096,'stdout_bytes':8*1024*1024,'stderr_bytes':8*1024*1024,'attempts':1},'expires_at':expires,'historical_cleanup':'NOT_ESTABLISHED','bootstrap_accepted':False,'production_qualified':False,'provider_access':False,'credential_access':False,'broker_connected':False,'paper_order_permission':False,'trade_execution_permission':False,'live_execution':False,'new_reference_requires':'OFFLINE_IDENTITY_REVIEW_AND_EXACT_COMMIT_GREEN_CI'}
desc=put('DESCRIPTOR.json',descriptor)
child=R/'diagnostic-child.py'
read_files=[str(B/x['path']) for x in seal['files']]+[str(child)]
binding={'descriptor_parent':sha(desc),'source_commit':HEAD,'boot_session_uuid':boot,'runtime_root':str(B),'interpreter':str(B/'bin/python3.14'),'cache_uuid':osref['cache_uuid'],'cache_files':osref['signed_files'],'catalog':catalog,'read_files':read_files,'discovery':regenerate(seal)}
prelude='''import sys, os
BINDING = BINDING_LITERAL
_READS=frozenset(BINDING['read_files'])
_DISCOVERY={BINDING['runtime_root']+'/'+k:tuple(v) for k,v in BINDING['discovery']}
def _sealed_cache(self):
    if self.path not in _DISCOVERY:raise PermissionError('UNPINNED_IMPORT_DIRECTORY')
    self._path_cache=set(_DISCOVERY[self.path]);self._relaxed_path_cache={n.lower() for n in _DISCOVERY[self.path]}
sys.modules['_frozen_importlib_external'].FileFinder._fill_cache=_sealed_cache
sys.path[:]=[BINDING['runtime_root']+'/lib/python3.14',BINDING['runtime_root']+'/lib/python3.14/lib-dynload']
sys.path_importer_cache.clear()
def _audit(event,args):
    if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.posix_spawn','os.exec','os.fork','os.forkpty','os.kill','os.killpg','os.listdir','os.scandir','os.remove','os.rmdir','os.rename','os.link','os.symlink','os.chown','os.truncate','os.mkdir','os.chmod','os.utime','os.setxattr','os.removexattr'):
        raise PermissionError('FORBIDDEN_EFFECT')
    if event=='open':
        path=args[0];mode=args[1];flags=args[2] or 0
        if not isinstance(path,(str,bytes)) or os.fsdecode(path) not in _READS or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND) or (isinstance(mode,str) and any(c in mode for c in 'wax+')):
            raise PermissionError('UNPINNED_FILE_OR_WRITE')
    if event=='ctypes.dlopen' and args[0] is not None:raise PermissionError('FOREIGN_LIBRARY')
    if event=='ctypes.dlsym' and args[1] not in ('_dyld_image_count','_dyld_get_image_name','_dyld_get_image_header','_dyld_get_image_vmaddr_slide','_dyld_get_shared_cache_uuid'):
        raise PermissionError('FOREIGN_SYMBOL')
    if event=='ctypes.string_at' and not (isinstance(args[0],int) and args[0]>0 and isinstance(args[1],int) and 0<args[1]<=65568):raise PermissionError('MEMORY_READ_BOUND')
sys.addaudithook(_audit)
'''.replace('BINDING_LITERAL',repr(binding))
put(child.name,(prelude+'\n'+source_text+'\nif __name__ == "__main__":\n    run(BINDING)\n').encode())
profile='''(version 1)
(allow default)
(deny network*)
(deny process-fork)
(deny process-exec)
(allow process-exec (literal INTERPRETER))
(deny file-write*)
(deny file-read-data)
(allow file-read-metadata)
; dyld startup requires opening the root directory itself, never its subtree.
(allow file-read-data (literal "/"))
(allow file-read-data (subpath BOOTSTRAP_PATH) (literal CHILD_PATH) (subpath "/System/Library") (subpath "/usr/lib") (subpath "/usr/share") (subpath "/System/Volumes/Preboot/Cryptexes/OS/System/Library") (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))
'''.replace('BOOTSTRAP_PATH',json.dumps(str(B))).replace('CHILD_PATH',json.dumps(str(child))).replace('INTERPRETER',json.dumps(str(B/'bin/python3.14')))
for path in (str(Path.home()/'.ssh'),str(Path.home()/'.aws'),str(Path.home()/'Library/Keychains'),'/Library/Keychains','/System/Library/Keychains'):
 profile+='(deny file-read* (subpath '+json.dumps(path)+'))\n'
profile_file=put('network-deny.sb',profile.encode())
attrs=[];pins=[]
def pin(path,meta=None):
 path=Path(path);s=path.lstat();kind=3 if path.is_symlink() else 2 if path.is_dir() else 1
 first=-1
 if meta is not None:
  first=len(attrs)
  for name,value in sorted(meta.items()):attrs.append((name,value['sha256'],value['size']))
 pins.append((str(path),sha(path) if kind==1 else '',os.readlink(path) if kind==3 else '',s.st_size if kind==1 else 0,stat.S_IMODE(s.st_mode),s.st_uid,kind,first,len(meta) if meta is not None else 0))
for rel,meta in sorted(seal['metadata'].items()):pin(B if rel=='.' else B/rel,meta)
for file in (desc,child,profile_file,catalog_file,cache_set,P/'evidence/FINAL-SEALED-BOOTSTRAP-V2.json',source_py,source_c):pin(file)
for file in ('/usr/bin/codesign','/usr/bin/sandbox-exec','/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal',str(stand)):pin(file)
for row in osref['signed_files']:
 p=Path(row['path']);s=p.lstat();assert s.st_size==row['size'] and s.st_uid==0
 # Rehash these independently at launch and after reaping; descriptor derives from independently signed cached evidence.
 pins.append((str(p),row['sha256'],'',s.st_size,stat.S_IMODE(s.st_mode),s.st_uid,1,-1,0))
sign_paths=[str(B/x['path']) for x in loads]+[x['path'] for x in osref['signed_files']]+[str(stand),'/usr/bin/codesign','/usr/bin/sandbox-exec','/System/Applications/Utilities/Terminal.app']
apple=[0]*len(loads)+[1]*(len(sign_paths)-len(loads))
q=lambda x:json.dumps(x,ensure_ascii=True)
header='static const Attr ATTRS[]={\n'+''.join('{'+q(n)+','+q(h)+','+str(s)+'},\n' for n,h,s in attrs)+'};\n'
header+='static const Pin PINS[]={\n'+''.join('{'+','.join([q(row[0]),q(row[1]),q(row[2])]+[str(x) for x in row[3:]])+'},\n' for row in pins)+'};\n#define PIN_COUNT '+str(len(pins))+'\n'
header+='static const char *SIGN_PATHS[]={'+','.join(q(p) for p in sign_paths)+'};\nstatic const int SIGN_APPLE[]={'+','.join(map(str,apple))+'};\n#define SIGN_COUNT '+str(len(sign_paths))+'\n'
constants={'QUALIFICATION':str(R.parent),'BOOT_UUID':boot,'OS_BUILD':osref['source_build'],'TERMINAL_EXE':'/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal','PACKAGE':str(R),'OUTPUT':str(R/'attempt-01'),'JOURNAL':str(R/'attempt-01/JOURNAL.txt'),'BOOTSTRAP':str(B),'PROFILE':str(profile_file),'INTERPRETER':str(B/'bin/python3.14'),'CHILD_SCRIPT':str(child),'CHILD_OUTPUT':str(R/'attempt-01/child.json'),'CHILD_ERROR':str(R/'attempt-01/child.stderr')}
header+=''.join('#define '+key+' '+q(value)+'\n' for key,value in constants.items())+'#define EXPIRES_AT '+str(expires)+'\n'
put('diagnostic_binding.h',header.encode());put('SUPERVISOR-PINS.json',{'pins':pins,'attributes':attrs,'signature_paths':sign_paths,'apple_anchor_required':apple})
print(json.dumps({'descriptor_sha256':sha(desc),'catalog_candidates':len(catalog),'count_is_not_acceptance':True,'pins':len(pins),'signature_checks_per_phase':len(sign_paths),'expires_at':expires,'native_execution':False}))
