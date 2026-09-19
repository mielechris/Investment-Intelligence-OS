"""Vendor framework stays at its signed installation path; only the venv is private."""
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import zipfile
from .state import require, file_hash, digest, decode, publish, directory

ENV = {'PATH':'/usr/bin:/bin:/usr/sbin', 'LC_ALL':'C', 'TZ':'UTC',
       'PYTHONDONTWRITEBYTECODE':'1', 'PIP_NO_INDEX':'1', 'PIP_DISABLE_PIP_VERSION_CHECK':'1',
       'PIP_CONFIG_FILE':'/dev/null', 'PIP_NO_CACHE_DIR':'1',
       'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':'/dev/null'}


def command(argv, *, timeout=30, cwd=None):
    result = subprocess.run(list(map(str, argv)), cwd=cwd, env=ENV, stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=timeout, close_fds=True)
    require(len(result.stdout)+len(result.stderr) <= 8*1024*1024, 'TOOL_OUTPUT_BOUND')
    require(result.returncode == 0, 'TOOL_FAILED:'+Path(str(argv[0])).name)
    return result.stdout.decode('utf-8')


def normalized(name):
    return re.sub('[-_.]+', '-', name).lower()


def lock_binding(lock, artifacts):
    rows = []
    for line in Path(lock).read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        require(re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+', line) is not None, 'LOCK_EXACT_ONLY')
        name, version = line.split('=='); rows.append((normalized(name), version))
    require(len(rows)==len(set(n for n,v in rows)), 'LOCK_DUPLICATE')
    pins = decode(Path(artifacts).read_bytes())
    require(pins['schema']==2 and pins['lock_sha256']==file_hash(lock), 'LOCK_PARENT')
    require(sorted(rows)==sorted((r['name'],r['version']) for r in pins['wheels']), 'LOCK_ARTIFACT_SET')
    require(len(pins['wheels'])==len(rows), 'ARTIFACT_DUPLICATE')
    for row in pins['wheels']:
        require(Path(row['filename']).name==row['filename'] and row['filename'].endswith('.whl'), 'WHEEL_NAME')
        require(re.fullmatch('[0-9a-f]{64}',row['sha256']) and type(row['size']) is int and row['size']>0, 'WHEEL_PIN')
    return pins


def verify_wheel(path, pin):
    require(path.stat().st_size==pin['size'] and file_hash(path)==pin['sha256'], 'WHEEL_HASH')
    py,abi,platform_tag=pin['filename'][:-4].rsplit('-',3)[-3:]
    require(platform_tag=='any' or all(t.endswith(('_arm64','_universal2')) for t in platform_tag.split('.')),'WHEEL_PLATFORM')
    require(py in ('py3','py2.py3','cp314') or (abi=='abi3' and re.fullmatch(r'cp3[0-9]+',py) and int(py[2:])<=314),'WHEEL_PYTHON')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names)==len(set(n.casefold() for n in names)), 'WHEEL_DUPLICATE')
        for item in archive.infolist():
            p = Path(item.filename)
            require(not p.is_absolute() and '..' not in p.parts and not stat.S_ISLNK(item.external_attr>>16), 'WHEEL_PATH')
            require(item.file_size < 256*1024*1024, 'WHEEL_MEMBER_BOUND')
            require(not item.filename.endswith('.pth'), 'EXECUTABLE_SITE_HOOK_NOT_ADMITTED')
        records = [n for n in names if n.endswith('.dist-info/RECORD')]
        require(len(records)==1, 'WHEEL_RECORD')
        seen = set()
        for name, encoding, size in csv.reader(io.StringIO(archive.read(records[0]).decode())):
            require(name in names and name not in seen, 'RECORD_MEMBERSHIP'); seen.add(name)
            if name==records[0]:
                require(not encoding and not size, 'RECORD_SELF'); continue
            data = archive.read(name)
            require(encoding.startswith('sha256=') and str(len(data))==size, 'RECORD_SIZE')
            require(base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()==encoding[7:], 'RECORD_HASH')
        require(seen=={n for n in names if not n.endswith('/')}, 'RECORD_CLOSURE')


def source_identity(root):
    root = Path(root).resolve()
    require(not command(['/usr/bin/git','status','--porcelain','--untracked-files=all'],cwd=root).strip(), 'SOURCE_DIRTY')
    commit = command(['/usr/bin/git','rev-parse','HEAD'],cwd=root).strip()
    files = {}
    for name in command(['/usr/bin/git','ls-files','-z'],cwd=root).split('\0'):
        if not name: continue
        p = root/name
        require(p.is_file() and not p.is_symlink(), 'SOURCE_FILE')
        files[name] = file_hash(p)
    return dict(commit=commit, inventory=files, inventory_sha256=digest(files))


def unchanged(root, source):
    require(source_identity(root)==source, 'SOURCE_CHANGED_DURING_QUALIFICATION')


def verify_vendor(config):
    python = Path(config['vendor_python'])
    require(str(python).startswith('/Library/Frameworks/Python.framework/Versions/3.14/'), 'VENDOR_LOCATION')
    resolved = python.resolve(strict=True)
    require(str(resolved).startswith('/Library/Frameworks/Python.framework/Versions/3.14/'), 'VENDOR_ALIAS')
    image=Path('/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python')
    for p in (resolved,image,*resolved.parents,*image.parents):
        st=p.stat(); require(st.st_uid==0 and not st.st_mode&0o002 and (not st.st_mode&0o020 or st.st_gid in (0,80)), 'VENDOR_OWNER_MODE')
    requirement = 'anchor apple generic and certificate leaf[subject.OU] = "BMM5U3QVKW"'
    command(['/usr/bin/codesign','--verify','--strict','--all-architectures','-R='+requirement,resolved])
    command(['/usr/bin/codesign','--verify','--strict','--all-architectures','-R='+requirement,image])
    library = Path('/Library/Frameworks/Python.framework/Versions/3.14/Python')
    command(['/usr/bin/codesign','--verify','--strict','--all-architectures','-R='+requirement,library])
    version = command([python,'-I','-B','-S','-c','import sys;print(".".join(map(str,sys.version_info[:3])))']).strip()
    require(version==config['python_version'], 'VENDOR_VERSION')
    return dict(launcher=str(python), launcher_sha256=file_hash(resolved), image=str(image), image_sha256=file_hash(image),
                framework_sha256=file_hash(library), version=version, signature_team='BMM5U3QVKW')


def native_dependencies(path, envroot):
    lines = command(['/usr/bin/otool','-L',path]).splitlines()
    dependencies = []
    load_commands = command(['/usr/bin/otool','-l',path]).splitlines()
    rpaths = []
    for index,line in enumerate(load_commands):
        if line.strip()=='cmd LC_RPATH':
            value=load_commands[index+2].strip().split(' (offset ')[0]
            require(value.startswith('path '),'RPATH_PARSE');rpaths.append(value[5:])
    def expand(value):
        return value.replace('@loader_path',str(path.parent)).replace('@executable_path',str(envroot/'bin'))
    for line in lines:
        if not line.startswith('\t'): continue
        value=line.strip().split(' (compatibility version')[0]
        if value.startswith('@rpath/'):
            candidates=[Path(expand(p))/value[7:] for p in rpaths]
            candidates=[p for p in candidates if p.exists()]
            require(len(candidates)==1,'NATIVE_RPATH_UNRESOLVED');target=str(candidates[0].resolve())
        else:target=expand(value)
        if target.startswith('/System/Library/') or target.startswith('/usr/lib/'):
            dependencies.append(dict(load=value,resolved=target,kind='OS_SHARED_CACHE'));continue
        require(not target.startswith('@'), 'NATIVE_DEPENDENCY_UNRESOLVED')
        p=Path(target).resolve(strict=True)
        require(p.is_relative_to(envroot) or str(p).startswith('/Library/Frameworks/Python.framework/Versions/3.14/'), 'NATIVE_DEPENDENCY_ESCAPE')
        dependencies.append(dict(load=value,resolved=str(p),sha256=file_hash(p)))
    require(dependencies, 'NATIVE_DEPENDENCIES_EMPTY')
    return dependencies


INVENTORY = r'''
import sys,sysconfig
sys.path.append(sysconfig.get_path('purelib'))
import importlib.metadata as m, json,sys,sysconfig,csv,base64,hashlib,pathlib
root=pathlib.Path(sys.prefix).resolve(); packages=[]
for d in m.distributions():
 files=[]
 for f in d.files or []:
  p=pathlib.Path(d.locate_file(f)).resolve()
  if not p.is_relative_to(root): raise ValueError('INSTALLED_ORIGIN_ESCAPE')
  if not p.is_file(): raise ValueError('INSTALLED_FILE_MISSING')
  b=p.read_bytes()
  if f.hash and (f.hash.mode!='sha256' or base64.urlsafe_b64encode(hashlib.sha256(b).digest()).rstrip(b'=').decode()!=f.hash.value): raise ValueError('INSTALLED_RECORD_HASH')
  if f.size is not None and len(b)!=f.size: raise ValueError('INSTALLED_RECORD_SIZE')
  files.append({'path':str(p.relative_to(root)),'sha256':hashlib.sha256(b).hexdigest()})
 if not files: raise ValueError('INSTALLED_RECORD_MISSING')
 packages.append({'name':d.metadata['Name'],'version':d.version,'files':sorted(files,key=lambda r:r['path'])})
print(json.dumps({'prefix':str(root),'base_prefix':sys.base_prefix,'executable':sys.executable,'packages':sorted(packages,key=lambda r:r['name'])}))
'''


BUILD_GUARD = """
import sys
sys.dont_write_bytecode=True
def no_external(event,args):
    if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.posix_spawn','os.fork','os.forkpty','os.exec'):
        raise PermissionError('BUILD_EXTERNAL_EFFECT_DENIED')
sys.addaudithook(no_external)
"""


def pip_command(python, wheel, arguments, *, timeout=180):
    script=BUILD_GUARD+"\nimport sysconfig,runpy\nsys.path.insert(0,sys.argv.pop(1))\nsys.path.append(sysconfig.get_path('purelib'))\nsys.argv[0]='pip'\nrunpy.run_module('pip',run_name='__main__')"
    return command([python,'-I','-B','-S','-c',script,wheel]+arguments,timeout=timeout)


def environment_tree(root):
    rows={}
    for p in sorted(root.rglob('*')):
        if p.name=='IIOS-RUNTIME.json':continue
        relative=str(p.relative_to(root))
        if p.is_symlink():
            target=p.resolve(strict=True)
            require(target.is_relative_to(root) or str(target).startswith('/Library/Frameworks/Python.framework/Versions/3.14/'),'VENV_LINK_ESCAPE')
            rows[relative]={'link':os.readlink(p)}
        elif p.is_file():rows[relative]={'sha256':file_hash(p)}
    return rows


def verify_environment_tree(root, expected):
    require(environment_tree(root)==expected,'RUNTIME_TREE_DRIFT')


def environment(root, config, lock, artifacts, *, rebuild=False):
    ENV['TMPDIR']=str(directory(root/'scratch'))
    vendor = verify_vendor(config)
    pins = lock_binding(lock, artifacts)
    wheelhouse = directory(root/'wheelhouse')
    for row in pins['wheels']:verify_wheel(wheelhouse/row['filename'],row)
    identity = digest(dict(vendor=vendor,lock=file_hash(lock),artifacts=file_hash(artifacts)))
    venv = root/('venv-'+identity)
    complete = venv/'IIOS-RUNTIME.json'
    bundled=list(Path('/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/ensurepip/_bundled').glob('pip-*.whl'))
    require(len(bundled)==1 and not bundled[0].is_symlink(),'VENDOR_PIP_BUNDLE')
    pip_wheel=bundled[0];pip_parent=file_hash(pip_wheel)
    if venv.exists() and rebuild:
        import uuid
        venv.rename(root/('retired-'+identity+'-'+uuid.uuid4().hex))
    if venv.exists() and complete.is_file():verify_environment_tree(venv,decode(complete.read_bytes())['tree'])
    if not venv.exists():
        command([vendor['launcher'],'-I','-B','-S','-c',BUILD_GUARD+'\nimport venv;venv.EnvBuilder(with_pip=False,symlinks=True).create(sys.argv[1])',venv],timeout=120)
        requirements=venv/'IIOS-REQUIREMENTS.txt'
        requirements.write_text('\n'.join(f"{r['name']}=={r['version']} --hash=sha256:{r['sha256']}" for r in pins['wheels'])+'\n')
        requirements.chmod(0o400)
        pip_command(venv/'bin/python',pip_wheel,['install','--no-index','--no-deps','--require-hashes',
                 '--only-binary=:all:','--no-compile','--no-cache-dir','--find-links',wheelhouse,'-r',requirements],timeout=180)
    else:
        require(complete.is_file(), 'PARTIAL_VENV_REQUIRES_EXPLICIT_REBUILD')
    pip_command(venv/'bin/python',pip_wheel,['check'])
    require(file_hash(pip_wheel)==pip_parent,'VENDOR_PIP_CHANGED')
    inventory = decode(command([venv/'bin/python','-I','-B','-S','-c',INVENTORY]))
    require(inventory['prefix']==str(venv) and inventory['base_prefix']=='/Library/Frameworks/Python.framework/Versions/3.14', 'VENV_BASE')
    require(len({normalized(p['name']) for p in inventory['packages']})==len(inventory['packages']),'INSTALLED_DUPLICATE')
    actual = {(normalized(p['name']),p['version']) for p in inventory['packages']}
    require(actual=={(p['name'],p['version']) for p in pins['wheels']},'INSTALLED_LOCK_SET')
    native = {}
    for p in sorted(venv.rglob('*')):
        if p.is_file() and not p.is_symlink() and p.suffix in ('.so','.dylib'):
            native[str(p.relative_to(venv))] = native_dependencies(p,venv)
    manifest = dict(identity=identity,vendor=vendor,lock=file_hash(lock),artifacts=file_hash(artifacts),
                    environment=inventory,native=native,tree=environment_tree(venv),vendor_pip_sha256=pip_parent)
    if complete.exists():require(decode(complete.read_bytes())==manifest,'RUNTIME_DRIFT')
    else:publish(complete,manifest)
    return dict(path=str(venv),manifest=manifest,manifest_sha256=file_hash(complete))
