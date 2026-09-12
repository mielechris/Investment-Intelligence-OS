"""Disposable hosted-macOS startup diagnostics. Never a production entrypoint.

Preparation has no provider/credential interface. Native execution invokes only
the independently pinned STARTUP_ONLY descriptor, once, in a fresh output root.
Only the export directory is uploaded; runtime/TLS private bytes stay local.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import ssl
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest

ARCHIVE_SHA256 = 'b9054a9d3d54f4cb5573d44907fddb29874b08909bde73f29f2868cf872223ee'
PYTHON_VERSION = '3.13.15'
FAILURES = frozenset(('EXACT_ROOT','ROOT_OWNERSHIP','HOSTED_IDENTITY','PROXY_REJECTED',
    'SOURCE_PIN','SOURCE_STATE','SOURCE_BYTES','PREPARATION_TOOL_FAILED','ARCHIVE_PIN',
    'ARCHIVE_MEMBERSHIP','ARCHIVE_PATH','ARCHIVE_LINK_CYCLE','ARCHIVE_LINK_TYPE',
    'ARCHIVE_LINK_ESCAPE','ARCHIVE_SIZE','RUNTIME_OWNERSHIP','RUNTIME_ALIAS',
    'RELOCATABLE_RUNTIME_IDENTITY','TLS_CONTEXT','IMPORT_CLOSURE','DYNAMIC_DEPENDENCY',
    'DIRECTORY_DESCRIPTOR','DIRECTORY_IDENTITY','DIRECTORY_ESCAPE','OFFLINE_COLLECTION',
    'OFFLINE_WRITE_BOUNDARY','OFFLINE_NATIVE_BOUNDARY','OFFLINE_FAILED','OFFLINE_REQUIRED',
    'OFFLINE_SOURCE_BINDING','STARTUP_ONLY_REQUIRED','ATTEMPT_ALREADY_EXISTS',
    'SUPERVISOR_FAILED','WORKER_EVIDENCE_FORBIDDEN','EVIDENCE_FILE','EVIDENCE_SCOPE','EVIDENCE_NAME'))
SOURCE_NAMES = (
    'alpha_session_execution.py', 'provider_gateway_https.py', 'alpha_market_baseline.py',
    'alpha_session_readiness.py', 'opportunity_spine_contract.py', 'provider_gateway_contract.py',
    'truth_spine_contract.py', 'truth_spine_process_identity.py', 'alpha_radar_admission.py',
    'alpha_radar_runner.py', 'alpha_radar_fixture.py', 'alpha_radar.sb.in')
REPO = Path(__file__).resolve().parents[2]
NATIVE_ONLY = frozenset({
    'test_truth_spine_process_identity.EphemeralMacOSTests.test_actual_launcher_stabilizes_with_actual_self_receipt'})


def require(value, code):
    if not value:
        raise ValueError(code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)+'\n').encode()


def put(path, data, mode=0o400):
    with path.open('xb') as stream:
        stream.write(data)
    path.chmod(mode)


def document(path, value):
    put(path, canonical(value))


def root_check(root):
    require(root.parent == Path('/private/tmp') and root.resolve() == root and
            root.name.startswith('iios-provider-connection-source-tests-') and
            not root.is_symlink(), 'EXACT_ROOT')
    st = root.stat()
    require(st.st_uid == os.getuid() and not st.st_mode & 0o077, 'ROOT_OWNERSHIP')


def hosted():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and
            os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted' and
            os.environ.get('RUNNER_OS') == 'macOS' and
            os.environ.get('RUNNER_ARCH') == 'ARM64' and
            os.environ.get('GITHUB_RUN_ATTEMPT') == '1' and
            platform.system() == 'Darwin' and platform.machine() == 'arm64' and
            platform.mac_ver()[0].split('.')[0] == '26', 'HOSTED_IDENTITY')
    # The job never passes ambient proxy/credential configuration to a child.
    require(not any(os.environ.get(k) for k in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY',
                                               'http_proxy','https_proxy','all_proxy')), 'PROXY_REJECTED')


def command(argv, *, cwd=None):
    """Preparation tools only; no raw stderr or exception text is retained."""
    result = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=30, check=False,
                            env={'PATH':'/usr/bin:/bin:/usr/sbin', 'LC_ALL':'C', 'TZ':'UTC'})
    require(result.returncode == 0 and len(result.stdout) <= 2_000_000, 'PREPARATION_TOOL_FAILED')
    return result.stdout


def materialize(archive, destination, expected=ARCHIVE_SHA256):
    """Hash-admitted archive; links become independent bytes before admission."""
    data = archive.read_bytes()
    require(digest(data) == expected, 'ARCHIVE_PIN')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as bundle:
        members = bundle.getmembers()
        by_name = {m.name:m for m in members}
        require(len(by_name) == len(members) and sum(m.size for m in members) <= 300_000_000,
                'ARCHIVE_MEMBERSHIP')
        for member in members:
            path = PurePosixPath(member.name)
            require(not path.is_absolute() and '..' not in path.parts and
                    path.parts[0] == 'python' and str(path) == member.name.rstrip('/') and
                    (member.isdir() or member.isfile() or member.issym() or member.islnk()), 'ARCHIVE_PATH')
        def regular(member, seen=()):
            require(member.name not in seen, 'ARCHIVE_LINK_CYCLE')
            if member.isfile():
                return member
            require(member.issym() or member.islnk(), 'ARCHIVE_LINK_TYPE')
            target = (PurePosixPath(member.name).parent / member.linkname if member.issym()
                      else PurePosixPath(member.linkname))
            require(not target.is_absolute() and '..' not in target.parts and
                    str(target) in by_name, 'ARCHIVE_LINK_ESCAPE')
            return regular(by_name[str(target)], (*seen, member.name))
        destination.mkdir(mode=0o700)
        for member in members:
            path = destination / member.name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if member.isdir():
                path.mkdir(exist_ok=True, mode=0o700)
            else:
                source = regular(member)
                with bundle.extractfile(source) as stream:
                    content = stream.read()
                require(len(content) == source.size, 'ARCHIVE_SIZE')
                put(path, content, 0o500 if source.mode & 0o111 else 0o400)


def prepare(root, commit):
    hosted(); root_check(root)
    require(re.fullmatch('[a-f0-9]{40}', commit) and os.environ['GITHUB_SHA'] == commit,
            'SOURCE_PIN')
    require(command(['/usr/bin/git', 'rev-parse', 'HEAD'], cwd=REPO).decode().strip() == commit and
            command(['/usr/bin/git', 'status', '--porcelain'], cwd=REPO) == b'', 'SOURCE_STATE')
    runtime, out, exported = root/'runtime', root/'execution-output', root/'export'
    require(not out.exists() and not (root/'confinement-denied-input').exists(), 'ATTEMPT_ALREADY_EXISTS')
    materialize(root/'python-runtime.tar.gz', runtime)
    source = runtime/'source'; source.mkdir(mode=0o700)
    source_inventory = []
    for name in SOURCE_NAMES:
        relative = ('tests/native/' if name.startswith('alpha_radar') else 'BACK END/backend/')+name
        path = REPO/relative
        data = path.read_bytes()
        require(not path.is_symlink() and data == command(['/usr/bin/git','show',commit+':'+relative], cwd=REPO),
                'SOURCE_BYTES')
        put(source/name, data)
        source_inventory.append({'path':relative, 'size':len(data), 'sha256':digest(data)})
    fixture = runtime/'fixture'; fixture.mkdir(mode=0o700)
    config = root/'certificate.cnf'
    put(config, b'[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=ext\n'
        b'[dn]\nCN=Alpha Radar SYNTHETIC TEST ONLY\n[ext]\nsubjectAltName=IP:127.0.0.1\n'
        b'basicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n'
        b'extendedKeyUsage=serverAuth\n')
    command(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-sha256','-days','1',
             '-config',str(config),'-keyout',str(fixture/'private-key.pem'),'-out',str(fixture/'certificate.pem')])
    for path in fixture.iterdir(): path.chmod(0o400)
    document(fixture/'responses.json', {'scope':'SYNTHETIC_TEST_ONLY','faults':{}})
    # Preparation never binds a port. Availability is independently checked by
    # the pinned supervisor immediately before its one fixture launch.
    port = 38493
    sys.path[:0] = [str(source)]
    from alpha_radar_runner import confinement_profile
    put(runtime/'confinement.sb', confinement_profile(runtime,out,runtime/'python/bin/python3.13',port).encode())
    for path in sorted(runtime.rglob('*'), key=lambda p:len(p.parts), reverse=True):
        if path.is_dir(): path.chmod(0o500)
    runtime.chmod(0o500)
    rows=[]
    for path in sorted(runtime.rglob('*')):
        st=path.stat(follow_symlinks=False)
        require(not path.is_symlink() and st.st_uid == os.getuid() and not st.st_mode & 0o222,
                'RUNTIME_OWNERSHIP')
        if path.is_file():
            require(st.st_nlink == 1, 'RUNTIME_ALIAS')
            rows.append({'path':path.relative_to(runtime).as_posix(), 'size':st.st_size,
                         'sha256':digest(path.read_bytes()), 'mode':stat.S_IMODE(st.st_mode)})
    document(root/'runtime-rows.json', rows)
    document(exported/'source-inventory.json', source_inventory)
    document(exported/'environment.json', {
        'scope':'SYNTHETIC_TEST_ONLY','source_commit':commit,'run_id':os.environ['GITHUB_RUN_ID'],
        'run_attempt':1,'image_os':os.environ.get('ImageOS'), 'image_version':os.environ.get('ImageVersion'),
        'macos':command(['/usr/bin/sw_vers','-productVersion']).decode().strip(),
        'os_build':command(['/usr/bin/sw_vers','-buildVersion']).decode().strip(),
        'architecture':platform.machine(),'bootstrap_python':platform.python_version(),
        'runtime_archive_sha256':ARCHIVE_SHA256,'runtime_files':len(rows),
        'runtime_bytes':sum(v['size'] for v in rows), 'root':str(root),
        'tools':{p:digest(Path(p).read_bytes()) for p in
                 ('/usr/bin/sandbox-exec','/bin/ps','/usr/sbin/lsof','/usr/bin/openssl','/usr/bin/otool')},
        'system_libraries':'BOUND_TO_RECORDED_MACOS_BUILD', 'local_mac_qualification':'NOT_ESTABLISHED'})


def dependency_rows(runtime, path, listing, install_ids, load_commands, known):
    """Separate LC_ID_DYLIB identity from LC_LOAD_* dependencies; resolve LC_RPATH."""
    require(len(install_ids)<=1,'DYNAMIC_DEPENDENCY')
    targets=[line.strip().split(' (compatibility version')[0] for line in listing]
    if install_ids:
        identity=install_ids[0].strip()
        require(identity in (path.name,'@rpath/'+path.name) and targets and targets[0]==identity,
                'DYNAMIC_DEPENDENCY')
        targets=targets[1:]
    rpaths=[]
    for i,line in enumerate(load_commands):
        if line.strip()=='cmd LC_RPATH':
            require(i+2<len(load_commands),'DYNAMIC_DEPENDENCY')
            match=re.fullmatch(r'\s*path (.+) \(offset [0-9]+\)',load_commands[i+2])
            require(match is not None,'DYNAMIC_DEPENDENCY')
            rpaths.append(match[1])
    def resolve(target):
        if target.startswith('@loader_path/'):
            value=path.parent/target.removeprefix('@loader_path/')
        elif target.startswith('@executable_path/'):
            value=runtime/'python/bin'/target.removeprefix('@executable_path/')
        else:
            raise ValueError('DYNAMIC_DEPENDENCY')
        resolved=value.resolve()
        require(resolved.is_relative_to(runtime),'DYNAMIC_DEPENDENCY')
        return resolved
    bases=[resolve(v) for v in rpaths]
    linked=[]
    for target in targets:
        if target.startswith(('/usr/lib/','/System/Library/')):
            require('..' not in PurePosixPath(target).parts,'DYNAMIC_DEPENDENCY')
            linked.append(target);continue
        if target.startswith('@rpath/'):
            candidates=[(base/target.removeprefix('@rpath/')).resolve() for base in bases]
            require(candidates and all(v.is_relative_to(runtime) for v in candidates),'DYNAMIC_DEPENDENCY')
            candidates=[v for v in candidates if v.is_file()]
            require(len(set(candidates))==1,'DYNAMIC_DEPENDENCY')
            resolved=candidates[0]
        else:
            resolved=resolve(target)
        require(resolved.is_file() and resolved.relative_to(runtime).as_posix() in known,'DYNAMIC_DEPENDENCY')
        linked.append(resolved.relative_to(runtime).as_posix())
    return {'path':path.relative_to(runtime).as_posix(),'install_id':install_ids,
            'runtime_search_paths':[v.relative_to(runtime).as_posix() for v in bases],
            'dependencies':linked}


def finalize(root, commit):
    hosted(); root_check(root)
    runtime=root/'runtime'; out=root/'execution-output'
    require(Path(sys.executable).resolve() == runtime/'python/bin/python3.13' and
            sys.prefix == str(runtime/'python') and platform.python_version() == PYTHON_VERSION,
            'RELOCATABLE_RUNTIME_IDENTITY')
    sys.path[:0]=[str(runtime/'source')]
    from alpha_market_baseline import radar_plan
    from opportunity_spine_contract import schedule
    from provider_gateway_contract import content_hash
    from alpha_radar_admission import SCOPE, AUTHORITY, verify_inputs
    from alpha_radar_runner import STARTUP_SCHEMA, STARTUP_MODE, descriptor_schema, verify_tools
    rows=json.loads((root/'runtime-rows.json').read_bytes())
    dependencies=[]
    for row in rows:
        path=runtime/row['path']
        with path.open('rb') as stream: magic=stream.read(4)
        if magic not in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe'):
            continue
        lines=command(['/usr/bin/otool','-L',str(path)]).decode('utf-8').splitlines()[1:]
        install_ids=command(['/usr/bin/otool','-D',str(path)]).decode('utf-8').splitlines()[1:]
        load_commands=command(['/usr/bin/otool','-l',str(path)]).decode('utf-8').splitlines()
        dependencies.append(dependency_rows(runtime,path,lines,install_ids,load_commands,{v['path'] for v in rows}))
    document(root/'export'/'dynamic-dependencies.json',dependencies)
    r={'scope':SCOPE,'source_commit':commit,'root':str(runtime),'files':rows,
       'interpreter':'python/bin/python3.13','tls':'fixture/certificate.pem',
       'source_files':sorted('source/'+name for name in SOURCE_NAMES),'confinement':'confinement.sb'}
    calendar={'calendar':'XNYS','session':'2026-09-14','open':'2026-09-14T13:30:00+00:00',
              'close':'2026-09-14T20:00:00+00:00'}
    universe={'symbols':[f'S{i:03}' for i in range(517)]}
    sched=schedule(universe,content_hash(universe),calendar,content_hash(calendar),
                   mode='FULL_OPPORTUNITY_RADAR',root=str(out/'journal'))
    plan=radar_plan(universe,content_hash(universe),calendar,content_hash(calendar),root=str(out/'journal'),
                    opportunity_schedule=sched,schedule_hash=content_hash(sched))
    f={'scope':SCOPE,'address':'127.0.0.1','server_name':'127.0.0.1','port':38493,
       'certificate':r['tls'],'certificate_sha256':digest((runtime/r['tls']).read_bytes()),
       'private_key':'fixture/private-key.pem','responses':'fixture/responses.json',
       'responses_sha256':digest((runtime/'fixture/responses.json').read_bytes())}
    profile_hash=digest((runtime/'confinement.sb').read_bytes())
    p={'schema':'iios-alpha-radar-synthetic-package-v1','scope':SCOPE,'source_commit':commit,
       'runtime_parent':content_hash(r),'plan':plan,'plan_parent':content_hash(plan),
       'fixture':f,'fixture_parent':content_hash(f),'confinement_parent':profile_hash,
       'root':str(out),'authority':AUTHORITY}
    pins={'package':content_hash(p),'runtime':content_hash(r),'plan':content_hash(plan),
          'universe':content_hash(universe),'schedule':content_hash(sched),
          'fixture':content_hash(f),'confinement':profile_hash}
    verify_inputs(p,r,pins,root)
    tools={v:digest(Path(v).read_bytes()) for v in ('/usr/bin/sandbox-exec','/bin/ps','/usr/sbin/lsof')}
    verify_tools(tools)
    d={'schema':STARTUP_SCHEMA,'execution_mode':STARTUP_MODE,'package':p,'runtime':r,
       'expected':pins,'authorized_root':str(root),'native_tools':tools,
       'clock_mode':'STARTUP_WALL_CLOCK','maximum_duration_seconds':120}
    descriptor_schema(d)
    # Import and local context validation: no listener, handshake or credential.
    context=ssl.create_default_context(cafile=str(runtime/r['tls']))
    require(context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED,'TLS_CONTEXT')
    server=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(str(runtime/f['certificate']),str(runtime/f['private_key']))
    known={v['path'] for v in rows}
    for name,module in tuple(sys.modules.items()):
        path=getattr(module,'__file__',None)
        if path and name != '__main__':
            resolved=Path(path).resolve()
            require(resolved.is_relative_to(runtime) and resolved.relative_to(runtime).as_posix() in known,
                    'IMPORT_CLOSURE')
    document(root/'descriptor.json',d)
    document(root/'export'/'prepared-pins.json',{'scope':SCOPE,'source_commit':commit,
        'descriptor_sha256':content_hash(d),'parents':pins,'runtime':r,'address':'127.0.0.1','port':38493,
        'openssl':ssl.OPENSSL_VERSION,'python':platform.python_version(),'authority':AUTHORITY,
        'execution_mode':STARTUP_MODE,'http_requests':0,'worker_launches':0,'production':'NOT_QUALIFIED'})


def offline_partition(suite):
    tests=[]
    def flatten(value):
        for test in value:
            if isinstance(test,unittest.TestSuite): flatten(test)
            else: tests.append(test)
    flatten(suite)
    ids=[t.id() for t in tests]
    require(len(ids)==len(set(ids)) and not any('_FailedTest' in v for v in ids) and
            NATIVE_ONLY <= set(ids),'OFFLINE_COLLECTION')
    selected=[t for t in tests if t.id() not in NATIVE_ONLY]
    return unittest.TestSuite(selected), {'collected':ids,'offline':[t.id() for t in selected],
        'native_not_run':[{'node':v,'reason':'Preexisting opt-in real framework launcher; not a mocked test',
                          'classification':'NOT RUN — SEPARATE NATIVE GATE'} for v in sorted(NATIVE_ONLY)]}


def binding_paths():
    return sorted({('tests/native/' if name.startswith('alpha_radar') else 'BACK END/backend/')+name
                   for name in SOURCE_NAMES} | {
        'tests/native/alpha_radar_ci.py', 'tests/native/test_alpha_radar_native.py',
        'BACK END/backend/test_truth_spine_process_identity.py',
        '.github/workflows/alpha-radar-native-diagnostics.yml'})


def source_bindings():
    return {name:digest((REPO/name).read_bytes()) for name in binding_paths()}


def verify_bindings(expected):
    # Never turn untrusted receipt keys into filesystem paths.
    require(type(expected) is dict and set(expected)==set(binding_paths()),'OFFLINE_SOURCE_BINDING')
    require(expected==source_bindings(),'OFFLINE_SOURCE_BINDING')


def offline(root):
    """Every native-harness test is mocked; an audit hook rejects OS dispatch."""
    root_check(root)
    bindings_before=source_bindings()
    test_root=Path(tempfile.mkdtemp(prefix='iios-provider-connection-source-tests-ci-offline-',dir='/private/tmp'))
    root_check(test_root)
    sys.path[:0]=[str(REPO/'tests/native'),str(REPO/'BACK END/backend')]
    os.environ['IIOS_GATEWAY_TEST_ROOT']=str(test_root); tempfile.tempdir=str(test_root)
    sys.dont_write_bytecode=True
    original_open=os.open; registered={}; active=[None]
    def guarded_open(path,flags,mode=0o777,*,dir_fd=None):
        resolved=Path(path).resolve() if isinstance(path,(str,os.PathLike)) and dir_fd is None else None
        if dir_fd is not None:
            require(dir_fd in registered,'DIRECTORY_DESCRIPTOR')
            parent,identity=registered[dir_fd]; st=os.fstat(dir_fd)
            require((st.st_dev,st.st_ino)==identity and parent.resolve()==parent,'DIRECTORY_IDENTITY')
            resolved=(parent/path).resolve()
            require(resolved.is_relative_to(test_root) or resolved.is_relative_to(root),'DIRECTORY_ESCAPE')
        previous=active[0];active[0]=(path,resolved)
        try: fd=original_open(path,flags,mode,dir_fd=dir_fd)
        finally: active[0]=previous
        st=os.fstat(fd)
        if stat.S_ISDIR(st.st_mode) and resolved is not None and (
                resolved.is_relative_to(test_root) or resolved.is_relative_to(root)):
            registered[fd]=(resolved,(st.st_dev,st.st_ino))
        return fd
    os.open=guarded_open
    def audit(event,args):
        if event=='os.kill' and args==(os.getpid(),0): return
        if event in ('socket.__new__','socket.connect','socket.bind','subprocess.Popen','os.system',
                     'os.posix_spawn','os.kill','os.killpg','ctypes.dlopen'):
            raise PermissionError('OFFLINE_NATIVE_BOUNDARY')
        if event=='open':
            path,mode,flags=args
            writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC))
            if writing and not isinstance(path,int):
                resolved=active[0][1] if active[0] and active[0][0]==path else Path(path).resolve()
                require(resolved is not None and (resolved.is_relative_to(test_root) or
                        resolved.is_relative_to(root)),'OFFLINE_WRITE_BOUNDARY')
    sys.addaudithook(audit)
    names=['test_alpha_radar_native','test_truth_spine_process_identity']
    suite,partition=offline_partition(unittest.defaultTestLoader.loadTestsFromNames(names))
    ids=partition['offline']
    document(root/'export'/'offline-collection.json',partition)
    result=unittest.TestResult();result.failfast=True
    suite.run(result)
    document(root/'export'/'offline-results.json',{'collected':len(ids),'executed':result.testsRun,
        'passed':result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
        'failed':[t.id() for t,_ in result.failures], 'errors':[t.id() for t,_ in result.errors],
        'skipped':[t.id() for t,_ in result.skipped], 'success':result.wasSuccessful(),
        'scope':'MOCKED_OFFLINE_ONLY','test_root':str(test_root),
        'source_bindings':bindings_before,
        'failure_text':'NOT_RETAINED_UNRESTRICTED'})
    require(result.wasSuccessful() and result.testsRun==len(ids) and not result.skipped,'OFFLINE_FAILED')
    verify_bindings(bindings_before)


def execute(root):
    hosted();root_check(root)
    runtime=root/'runtime';out=root/'execution-output'
    sys.path[:0]=[str(runtime/'source')]
    from alpha_radar_runner import (read_descriptor, descriptor_schema, startup_only,
        StderrCapture, verify_startup_result, verify_tools)
    from alpha_radar_admission import verify_inputs, verify_envelope
    from provider_gateway_contract import content_hash
    pins=json.loads((root/'export'/'prepared-pins.json').read_bytes())
    d=read_descriptor(root/'descriptor.json',pins['descriptor_sha256'])
    descriptor_schema(d);require(startup_only(d),'STARTUP_ONLY_REQUIRED')
    verify_inputs(d['package'],d['runtime'],d['expected'],root);verify_tools(d['native_tools'])
    require(not out.exists() and not (root/'confinement-denied-input').exists() and
            not (root/'native-attempt.json').exists(),'ATTEMPT_ALREADY_EXISTS')
    offline_result=json.loads((root/'export'/'offline-results.json').read_bytes())
    require(offline_result['success'] is True and not offline_result['skipped'] and
            offline_result['collected']==offline_result['executed'],'OFFLINE_REQUIRED')
    verify_bindings(offline_result['source_bindings'])
    document(root/'native-attempt.json',{'descriptor_parent':pins['descriptor_sha256'],
                                       'attempt':1,'execution_mode':d['execution_mode']})
    argv=[str(runtime/'python/bin/python3.13'),'-B',str(runtime/'source/alpha_radar_runner.py'),
          '--descriptor',str(root/'descriptor.json'),'--expected-descriptor',pins['descriptor_sha256']]
    # No raw stdout/stderr file; the child receives no CI token, proxy or account environment.
    child=subprocess.Popen(argv,cwd=root,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,close_fds=True,env={'PATH':'/usr/bin:/bin:/usr/sbin','LC_ALL':'C','TZ':'UTC'})
    capture=StderrCapture(child.stderr);started=time.monotonic()
    # The pinned supervisor/fixture enforce bounded deadlines and owned cleanup.
    # On an outer timeout we do not signal an unverified supervisor or claim cleanup.
    while child.poll() is None and time.monotonic()-started < 180:
        capture.drain();time.sleep(.05)
    capture.drain()
    if child.poll() is not None: capture.finish()
    value={'scope':'SYNTHETIC_TEST_ONLY','execution_mode':d['execution_mode'],
        'descriptor_parent':pins['descriptor_sha256'],'supervisor_pid':child.pid,
        'supervisor_exit_code':child.returncode if child.returncode is not None and child.returncode>=0 else None,
        'supervisor_signal':-child.returncode if child.returncode is not None and child.returncode<0 else None,
        'supervisor_exited':child.returncode is not None,'diagnostics':capture.snapshot(),
        'cleanup':'REQUIRES_VERIFIED_SUPERVISOR_RECEIPT','requests':0,'worker_launches':0,
        'authority':d['package']['authority'],'production':'NOT_QUALIFIED'}
    document(root/'export'/'supervisor-result.json',value)
    require(child.returncode == 0 and not capture.overflow,'SUPERVISOR_FAILED')
    doc=json.loads((out/'final-audit.json').read_bytes())
    result=verify_envelope(doc,content_hash(doc),parents=d['expected'])
    verify_startup_result(result,pins['descriptor_sha256'])
    require(not (out/'worker-launch.json').exists() and not (out/'session.json').exists() and
            not (out/'journal').exists(),'WORKER_EVIDENCE_FORBIDDEN')


def export(root):
    """Only structured synthetic records and positively sanitized diagnostics."""
    root_check(root); destination=root/'export'
    out=root/'execution-output'
    if out.is_dir() and not out.is_symlink():
        for path in sorted(out.glob('*.json')):
            require(not path.is_symlink() and path.stat().st_size<=8_000_000,'EVIDENCE_FILE')
            value=json.loads(path.read_bytes())
            require(value.get('scope')=='SYNTHETIC_TEST_ONLY','EVIDENCE_SCOPE')
            # Receipt producers have positive schemas; no arbitrary child files or TLS keys.
            allowed=(re.fullmatch(r'(fixture-launch|fixture-startup|fixture-ack|native-failure|final-audit|'
                                 r'fixture-diagnostic-[0-9]{4}|lifecycle-[0-9]{4})\.json',path.name))
            require(allowed is not None,'EVIDENCE_NAME')
            document(destination/path.name,value)
    rows=[{'path':p.name,'size':p.stat().st_size,'sha256':digest(p.read_bytes())}
          for p in sorted(destination.iterdir()) if p.is_file()]
    document(destination/'EVIDENCE-INVENTORY.json',rows)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=('prepare','finalize','offline','execute','export'))
    parser.add_argument('--root',required=True);parser.add_argument('--commit')
    args=parser.parse_args();root=Path(args.root)
    try:
        if args.phase in ('prepare','finalize'): globals()[args.phase](root,args.commit)
        else: globals()[args.phase](root)
        return 0
    except Exception as error:
        # Preserve the stage and fixed category without exception strings or traceback.
        category=type(error).__name__ if type(error) in (ValueError,PermissionError,FileExistsError,
                     FileNotFoundError,TimeoutError,subprocess.TimeoutExpired) else 'UNCLASSIFIED_ERROR'
        code=error.args[0] if error.args and type(error.args[0]) is str and error.args[0] in FAILURES else 'UNCLASSIFIED_ERROR'
        root_check(root)
        document(root/'export'/(args.phase+'-failure.json'),
                 {'scope':'SYNTHETIC_TEST_ONLY','phase':args.phase,'category':category,'code':code,
                  'production':'NOT_QUALIFIED','raw_error_retained':False})
        print('SYNTHETIC_CI_PHASE_FAILED: '+args.phase)
        return 1


if __name__=='__main__':
    sys.exit(main())
