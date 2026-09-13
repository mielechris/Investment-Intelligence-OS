"""Disposable hosted-macOS startup diagnostics. Never a production entrypoint.

Preparation has no provider/credential interface. Native execution invokes only
the independently pinned STARTUP_ONLY descriptor, once, in a fresh output root.
Only the export directory is uploaded; runtime/TLS private bytes stay local.
"""
import argparse
# Standard-library initialization precedes the preparation boundary, like ssl.
# No sandbox/inspection library is loaded here; later ctypes loads remain denied.
import ctypes
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
    'NATIVE_EXECUTION_NOT_AUTHORIZED','PREPARATION_NATIVE_BOUNDARY','STATIC_IDENTITY',
    'PREPARATION_SOCKET_REJECTED','PREPARATION_CTYPES_REJECTED','PREPARATION_SIGNAL_REJECTED',
    'PREPARATION_SHELL_REJECTED','PREPARATION_SPAWN_REJECTED',
    'PROFILE_PROBE_EVENT','PROFILE_PROBE_PROFILE','PROFILE_PROBE_LIMIT','PROFILE_PROBE_SPAWN',
    'PROFILE_PROBE_TIMEOUT','PROFILE_PROBE_SANITIZATION',
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


def native_execution_allowed(event_name, event, explicit_request):
    """Exact manual event AND explicit CLI request; absent/invalid values deny."""
    if event_name != 'workflow_dispatch' or explicit_request is not True or type(event) is not dict:
        return False
    inputs = event.get('inputs')
    if type(inputs) is not dict:
        return False
    value = inputs.get('native_startup')
    return value is True or (type(value) is str and value == 'true')


def require_execution_source(expected, actual, ref):
    """Independent owner input must equal the workflow event's immutable SHA."""
    require(type(expected) is str and re.fullmatch(r'[0-9a-f]{40}', expected) is not None and
            expected == actual and ref == 'refs/heads/feature/iios-provider-gateway-superbatch-1',
            'SOURCE_PIN')


def require_native_execution(explicit_request):
    require(os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch' and
            explicit_request is True, 'NATIVE_EXECUTION_NOT_AUTHORIZED')
    try:
        path = Path(os.environ['GITHUB_EVENT_PATH'])
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 1_000_000,
                'NATIVE_EXECUTION_NOT_AUTHORIZED')
        with path.open('rb') as stream:
            raw = stream.read(1_000_001)
        require(len(raw) <= 1_000_000, 'NATIVE_EXECUTION_NOT_AUTHORIZED')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, 'NATIVE_EXECUTION_NOT_AUTHORIZED')
                result[key] = value
            return result
        event = json.loads(raw, object_pairs_hook=unique)
    except (KeyError, OSError, ValueError):
        raise ValueError('NATIVE_EXECUTION_NOT_AUTHORIZED') from None
    require(native_execution_allowed(os.environ['GITHUB_EVENT_NAME'], event, explicit_request),
            'NATIVE_EXECUTION_NOT_AUTHORIZED')


def preparation_audit(event, args):
    """Defense in depth: preparation can inspect/build inputs, never launch native targets."""
    if event in ('socket.__new__', 'socket.connect', 'socket.bind'):
        raise PermissionError('PREPARATION_SOCKET_REJECTED')
    if event == 'ctypes.dlopen':
        raise PermissionError('PREPARATION_CTYPES_REJECTED')
    if event == 'os.system':
        raise PermissionError('PREPARATION_SHELL_REJECTED')
    if event == 'os.killpg' or (event == 'os.kill' and args != (os.getpid(), 0)):
        raise PermissionError('PREPARATION_SIGNAL_REJECTED')
    if event in ('subprocess.Popen', 'os.posix_spawn'):
        # CPython may use either process backend for the same reviewed tool.
        # Apply the identical positive admission to both; no new target is allowed.
        if len(args) < 2:
            raise PermissionError('PREPARATION_SPAWN_REJECTED')
        executable, argv = args[:2]
        allowed = {'/usr/bin/git': {'rev-parse', 'status', 'show'},
                   '/usr/bin/otool': {'-L', '-D', '-l'},
                   '/usr/bin/sw_vers': {'-productVersion', '-buildVersion'},
                   '/usr/bin/openssl': {'req'}}
        require(type(argv) in (list, tuple) and len(argv) >= 2 and
                executable in allowed and argv[0] == executable and argv[1] in allowed[executable],
                'PREPARATION_NATIVE_BOUNDARY')


# Candidate literals are inspected, not assumed to be complete message templates.
# Only finite IDs/counts are exported. No arbitrary binary strings or stderr.
STATIC_LITERALS = {
    'PROFILE_COMPILE_LITERAL': b'profile compilation failed',
    'PROFILE_APPLY_LITERAL': b'sandbox_apply',
    'EXECVP_FORMAT_LITERAL': b"execvp() of '%s' failed",
    'ENTITLEMENTS_LITERAL': b'failed to parse entitlements plist',
    'USAGE_LITERAL': b'Usage: sandbox-exec [options] command [args]',
    'PROFILE_READ_FORMAT_LITERAL': b'read(%s)',
}
STATIC_PATHS = {'LAUNCHER': '/usr/bin/sandbox-exec',
                'SANDBOX_LIBRARY': '/usr/lib/libsandbox.1.dylib',
                'SANDBOX_LIBRARY_ALIAS': '/usr/lib/libsandbox.dylib'}


def literal_evidence(data):
    require(type(data) is bytes and len(data) <= 16_000_000, 'STATIC_IDENTITY')
    return {name: min(data.count(pattern), 255) for name, pattern in STATIC_LITERALS.items()}


def static_image(path):
    if not path.exists():
        return {'status': 'NOT_AVAILABLE_AS_STANDALONE_FILE', 'templates': 'UNVERIFIED'}
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or path.is_symlink():
        return {'status': 'NOT_REGULAR_NO_FOLLOW', 'templates': 'UNVERIFIED'}
    require(st.st_uid == 0 and not st.st_mode & 0o022 and st.st_size <= 16_000_000, 'STATIC_IDENTITY')
    with path.open('rb') as stream:
        observed = os.fstat(stream.fileno())
        require((observed.st_dev, observed.st_ino) == (st.st_dev, st.st_ino), 'STATIC_IDENTITY')
        data = stream.read(16_000_001)
        after = os.fstat(stream.fileno())
    final = path.lstat()
    require(len(data) == st.st_size and (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) ==
            (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns), 'STATIC_IDENTITY')
    return {'status': 'STATIC_BYTES_VERIFIED', 'sha256': digest(data), 'size': len(data),
            'mode': stat.S_IMODE(st.st_mode), 'literal_counts': literal_evidence(data),
            'evidence_scope': 'STATIC_LITERAL_PRESENCE_ONLY', 'runtime_failure': 'NOT_ESTABLISHED'}


def static_provenance(root):
    environment = json.loads((root/'export/environment.json').read_bytes())
    images = {name: static_image(Path(path)) for name, path in STATIC_PATHS.items()}
    require(images['LAUNCHER'].get('sha256') == environment['tools']['/usr/bin/sandbox-exec'],
            'STATIC_IDENTITY')
    document(root/'export/launcher-static-provenance.json', {
        'scope': 'SYNTHETIC_TEST_ONLY', 'source_commit': environment['source_commit'],
        'environment_parent': digest((root/'export/environment.json').read_bytes()),
        'source_bindings': source_bindings(), 'images': images,
        'template_applicability': 'LITERALS_ONLY_FULL_TEMPLATES_UNVERIFIED',
        'compiler_cache_identity': 'NOT_COLLECTED_NO_CACHE_EXTRACTION',
        'historical_attempt_attribution': False, 'native_launches': 0,
        'raw_stderr_retained': False, 'arbitrary_strings_retained': False})


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
    static_provenance(root)


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


def execute(root, *, native_startup=False):
    require_native_execution(native_startup)
    require_execution_source(os.environ.get('IIOS_EXPECTED_SOURCE_COMMIT'),
                             os.environ.get('GITHUB_SHA'), os.environ.get('GITHUB_REF'))
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


# Separate compiler/launcher experiment: never a fixture qualification attempt.
PROBE_LIMIT = 10
PROBE_STDERR_LIMIT = 4096
PROBE_SECONDS = 10
PROBE_TAIL = ('-I', '-S', '-B', '-c', 'pass')
PROBE_ENV = {'PATH': '/usr/bin:/bin:/usr/sbin', 'LC_ALL': 'C', 'TZ': 'UTC'}
PROBE_WORDS = frozenset(('sandbox-exec profile compilation compile failed error syntax '
    'unbound variable unexpected token invalid unknown operation filter argument arguments '
    'while evaluating at line column of in on the a an is not supported permitted found '
    'permission denied no such file or directory execvp execution sandbox apply applying '
    'sandbox_apply sandbox_compile string number boolean expected got unexpected end '
    'version deny default allow file-read-metadata file-read file-write process-exec '
    'sysctl-read network-outbound network-inbound network-bind subpath literal remote '
    'local ip exit runtime library load loading image dyld Library loaded Reason tried '
    'Operation permitted undefined identifier reference evaluate failure read open '
    'RUNTIME WORKSPACE TEMP PROFILE INTERPRETER OUTPUT SYSTEM_LIBRARY USR_LIB DEVICE '
    'ROOT python3.13 DIAGNOSTIC_EXECUTABLE tcp').split())


def sanitize_probe_stderr(raw, replacements, *, overflow=False):
    """Positive vocabulary, not a template claim. Entire payload fails closed.

    No raw bytes, hashes, arbitrary identifiers, paths or exception messages leave
    this function. New words require source review, not a permissive fallback.
    """
    rejected = {'status': 'REJECTED', 'diagnostic': None, 'interpretation': 'UNKNOWN'}
    if type(raw) is not bytes or overflow or len(raw) > PROBE_STDERR_LIMIT:
        return {**rejected, 'reason': 'SIZE'}
    try:
        text = raw.decode('ascii')
    except UnicodeError:
        return {**rejected, 'reason': 'ENCODING'}
    # LF is the sole framing character. Tabs, CR, terminal escapes and DEL deny.
    if any((ord(c) < 32 and c != '\n') or ord(c) == 127 for c in text):
        return {**rejected, 'reason': 'CONTROL'}
    if re.search(r'(?i)(api.?key|secret|password|bearer|token\s*[=:]|https?://|-----BEGIN)', text):
        return {**rejected, 'reason': 'SENSITIVE'}
    # Replace complete quoted/unquoted path tokens, never retain an unknown suffix.
    for path, placeholder in sorted(replacements.items(), key=lambda v: len(v[0]), reverse=True):
        if not path.startswith('/') or placeholder not in PROBE_WORDS:
            return {**rejected, 'reason': 'REPLACEMENT'}
        text = re.sub(re.escape(path)+r'(?=$|[\s"\'):,])', '<'+placeholder+'>', text)
    if '/' in text or '\\' in text or '@' in text:
        return {**rejected, 'reason': 'PATH_OR_IDENTIFIER'}
    words = re.findall(r'[A-Za-z_][A-Za-z_0-9.\-]*', text)
    if any(word not in PROBE_WORDS for word in words):
        return {**rejected, 'reason': 'UNREVIEWED_TOKEN'}
    residue = re.sub(r'[A-Za-z_][A-Za-z_0-9.\-]*', '', text)
    if re.search(r'[^0-9\s<>():"\'.,;*+=?\-]', residue) or any(
            len(n) > 5 for n in re.findall(r'\d+', text)):
        return {**rejected, 'reason': 'UNREVIEWED_VALUE'}
    categories = []
    for category, patterns in (
        ('PROFILE_COMPILE_OUTPUT', ('unbound variable', 'syntax error', 'profile compilation failed')),
        ('OPERATION_FILTER_OUTPUT', ('invalid operation', 'unknown operation', 'unsupported filter')),
        ('PROFILE_APPLY_OUTPUT', ('sandbox_apply',)),
        ('EXECUTION_OUTPUT', ('execvp', 'Library not loaded', 'dyld'))):
        if any(pattern in text for pattern in patterns):
            categories.append(category)
    return {'status': 'SANITIZED', 'diagnostic': text, 'reason': None,
            'interpretation': categories[0] if len(categories) == 1 else 'UNKNOWN'}



def sanitize_probe_lines(raw, replacements, *, overflow=False):
    """Reject contaminated lines; never normalize controls into executable text.

    The original validator and its whole-message rejection contract are retained.
    This separate framing layer can retain independently validated clean lines.
    Missing context is explicit and never establishes a root cause by itself.
    """
    whole = sanitize_probe_stderr(raw, replacements, overflow=overflow)
    if whole['status'] == 'SANITIZED' or whole['reason'] != 'CONTROL':
        return whole
    # Check sensitive patterns across the original framing before any filtering.
    if re.search(rb'(?i)(api.?key|secret|password|bearer|token\s*[=:]|https?://|-----BEGIN)', raw):
        return {'status': 'REJECTED', 'diagnostic': None, 'interpretation': 'UNKNOWN', 'reason': 'SENSITIVE'}
    retained = []; rejected = []; interpretations = set()
    for index, line in enumerate(raw.split(b'\n'), 1):
        value = sanitize_probe_stderr(line, replacements)
        if value['status'] == 'SANITIZED':
            if value['diagnostic'].strip():
                retained.append(value['diagnostic'])
                interpretations.add(value['interpretation'])
        else:
            rejected.append({'line': index, 'reason': value['reason']})
    if not retained:
        return whole
    return {'status': 'PARTIALLY_SANITIZED', 'diagnostic': '\n'.join(retained),
            'interpretation': next(iter(interpretations)) if len(interpretations) == 1 else 'UNKNOWN',
            'reason': 'LINES_REJECTED', 'rejected_lines': rejected,
            'complete_launcher_message': False, 'root_cause': 'NOT_ESTABLISHED'}


def profile_clauses(text):
    """Split balanced top-level forms without interpreting the sandbox language."""
    forms = []; start = None; depth = 0; quoted = False; escaped = False
    for i, char in enumerate(text):
        if quoted:
            if escaped: escaped = False
            elif char == '\\': escaped = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        elif char == '(':
            if depth == 0: start = i
            depth += 1
        elif char == ')':
            depth -= 1
            require(depth >= 0, 'PROFILE_PROBE_PROFILE')
            if depth == 0: forms.append(text[start:i+1])
        elif depth == 0:
            require(char.isspace(), 'PROFILE_PROBE_PROFILE')
    require(not quoted and depth == 0 and len(forms) == 10 and
            forms[:2] == ['(version 1)', '(deny default)'], 'PROFILE_PROBE_PROFILE')
    expected = ('file-read-metadata', 'file-read*', 'file-write*', 'process-exec',
                'sysctl-read', 'network-outbound', 'network-inbound', 'network-bind')
    require(all(form.startswith('(allow '+op+')') or form.startswith('(allow '+op+' ')
                for form, op in zip(forms[2:], expected)), 'PROFILE_PROBE_PROFILE')
    return forms


def profile_matrix(exact):
    forms = profile_clauses(exact)
    # Every variant is a strict subset of the admitted profile. No substitute
    # allow rules, broadened paths, shell, public destination or policy edits.
    core = [0, 1, 3, 5]  # version, deny, exact reads, exact executable
    variants = [('EXACT', exact), ('READ_EXEC_CORE', '\n'.join(forms[i] for i in core)+'\n')]
    for index, name in ((2, 'METADATA'), (4, 'OUTPUT_WRITE'), (6, 'SYSCTL'),
                        (7, 'OUTBOUND'), (8, 'INBOUND'), (9, 'BIND')):
        variants.append(('CORE_PLUS_'+name, '\n'.join(forms[i] for i in sorted(core+[index]))+'\n'))
    variants.extend((('EXEC_WITHOUT_READ', '\n'.join(forms[i] for i in (0, 1, 5))+'\n'),
                     ('READ_WITHOUT_EXEC', '\n'.join(forms[i] for i in (0, 1, 3))+'\n')))
    require(len(variants) <= PROBE_LIMIT, 'PROFILE_PROBE_LIMIT')
    return variants


# Diagnostic executable is an OS-owned no-op, not Python or an adapter. Its
# dynamic loader dependencies remain bound to the observed signed OS image.
PROBE_EXECUTABLE = '/usr/bin/true'


def fixed_probe_executable():
    path = Path(PROBE_EXECUTABLE)
    st = path.lstat()
    require(path.resolve() == path and stat.S_ISREG(st.st_mode) and st.st_uid == 0
            and st.st_nlink == 1 and not st.st_mode & 0o022 and st.st_mode & 0o111
            and os.statvfs(path).f_flag & os.ST_RDONLY,
            'STATIC_IDENTITY')
    data = path.read_bytes()
    after = path.lstat()
    require((st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'STATIC_IDENTITY')
    return {'path': PROBE_EXECUTABLE, 'sha256': digest(data), 'size': len(data),
            'device': st.st_dev, 'inode': st.st_ino, 'mode': stat.S_IMODE(st.st_mode),
            'owner': st.st_uid, 'mtime_ns': st.st_mtime_ns, 'system_volume_readonly': True}


def grammar_matrix(exact):
    # Validate and preserve the original profile independently. These diagnostic
    # profiles do not replace it. Bare operations use DENY, testing registration
    # without admitting any outbound/inbound address. No profile allows writes.
    forms = profile_clauses(exact)
    core = ('(version 1)\n(deny default)\n'
            '(allow file-read* (literal "/usr/bin/true") '
            '(subpath "/System/Library") (subpath "/usr/lib"))\n')
    execute = '(allow process-exec (literal "/usr/bin/true"))\n'
    tcp = ('(allow network-outbound (remote tcp "127.0.0.1:38493"))',
           '(allow network-inbound (local tcp "127.0.0.1:38493"))',
           '(allow network-bind (local tcp "127.0.0.1:38493"))')
    variants = [('MINIMAL', ''), ('BARE_OUTBOUND', '(deny network-outbound)'),
        ('TCP_OUTBOUND', tcp[0]), ('BARE_INBOUND', '(deny network-inbound)'),
        ('TCP_INBOUND', tcp[1]), ('BARE_BIND', '(deny network-bind)'),
        ('TCP_BIND', tcp[2]), ('TCP_COMBINED', '\n'.join(tcp)),
        ('IP_NEGATIVE_CONTROL', '\n'.join(forms[7:10]))]
    # Only the three exact legacy loopback forms are admitted as negative input.
    require(tuple(forms[7:10]) == tuple(v.replace(' tcp ', ' ip ') for v in tcp),
            'PROFILE_PROBE_PROFILE')
    result = [(name, core+execute+extra+'\n') for name, extra in variants]
    result.append(('EXEC_DENIED_CONTROL', core))
    require(len(result) == PROBE_LIMIT == 10, 'PROFILE_PROBE_LIMIT')
    return result


def classify_probe(sanitized, code, eof, profile):
    """Observation and interpretation are separate; numeric exits aren't grammar.

    Zero from the pinned no-op establishes command execution and compilation.
    An exact retained execvp denial establishes the execution boundary. A source
    location alone or SIGABRT establishes neither compilation nor its cause.
    Positive language here is diagnostic interpretation, not a claimed private
    compiler message template. Incomplete/contradictory context stays UNKNOWN.
    """
    result = {'profile_compilation': 'UNKNOWN', 'command': 'UNKNOWN',
              'source_locations': [], 'basis': 'INSUFFICIENT_EVIDENCE'}
    if sanitized.get('status') not in ('SANITIZED', 'PARTIALLY_SANITIZED') or not eof:
        return result
    text = sanitized.get('diagnostic') or ''
    lines = profile.splitlines()
    for line, column in re.findall(r'(?m)^<PROFILE>:(\d{1,5}):(\d{1,5}):$', text):
        a, b = int(line), int(column)
        if 1 <= a <= len(lines) and 1 <= b <= len(lines[a-1])+1:
            result['source_locations'].append({'line': a, 'column': b})
    complete = sanitized.get('status') == 'SANITIZED'
    if type(code) is not int:
        return result
    if code == 0 and not text:
        return {**result, 'profile_compilation': 'PROFILE_COMPILE_ACCEPTED',
                'command': 'COMMAND_EXECUTED', 'basis': 'PINNED_NOOP_ZERO_EXIT'}
    if code < 0:
        return {**result, 'command': 'COMMAND_ABORTED',
                'basis': 'SIGNAL_OBSERVED_STAGE_UNKNOWN'}
    denial = "sandbox-exec: execvp() of '<DIAGNOSTIC_EXECUTABLE>' failed: Operation not permitted"
    if complete and code == 71 and text.strip() == denial:
        return {**result, 'profile_compilation': 'PROFILE_COMPILE_ACCEPTED',
                'command': 'COMMAND_DENIED', 'basis': 'EXACT_EXECVP_DENIAL_OBSERVED'}
    # Require a full isolated compile-error statement, consistent exit, valid
    # source location, and complete sanitized context. Never match substrings.
    allowed = re.compile(r'(?:sandbox-exec: |error: )?(?:unbound variable: '
        r'(?:remote|local|ip|tcp|network-bind)|profile compilation failed|syntax error)')
    semantic = [line for line in text.splitlines() if line and
                not re.fullmatch(r'<PROFILE>:\d{1,5}:\d{1,5}:', line)]
    if complete and code == 65 and result['source_locations'] and len(semantic) == 1 and allowed.fullmatch(semantic[0]):
        return {**result, 'profile_compilation': 'PROFILE_COMPILE_REJECTED',
                'basis': 'COMPLETE_COMPILE_DIAGNOSTIC_OBSERVED'}
    return result


def probe_spawn_audit(argv, cwd):
    """Closure admits one exact immutable command; no mutable execution mode."""
    exact = tuple(argv); directory = str(cwd)
    def audit(event, args):
        if event in ('subprocess.Popen', 'os.posix_spawn'):
            require(event == 'subprocess.Popen' and len(args) == 4 and
                    args[0] == exact[0] and tuple(args[1]) == exact and
                    str(args[2]) == directory and args[3] == PROBE_ENV,
                    'PROFILE_PROBE_SPAWN')
        else:
            preparation_audit(event, args)
    return audit


def probe_child(argv, cwd):
    # Popen's stderr is never redirected to a file or exception/log formatter.
    child = subprocess.Popen(argv, cwd=str(cwd), env=dict(PROBE_ENV), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, close_fds=True)
    os.set_blocking(child.stderr.fileno(), False)
    retained = bytearray(); overflow = False; eof = False; started = time.monotonic()
    try:
        while time.monotonic()-started < PROBE_SECONDS:
            try:
                chunk = os.read(child.stderr.fileno(), min(1024, PROBE_STDERR_LIMIT-len(retained)+1))
            except BlockingIOError:
                chunk = None
            if chunk == b'': eof = True
            elif chunk:
                remaining = PROBE_STDERR_LIMIT-len(retained)
                overflow = overflow or len(chunk) > remaining
                retained.extend(chunk[:remaining])
            if child.poll() is not None and eof: break
            time.sleep(.01)
        # Timeout is a hard stop, no further probes and no unverified PID signal.
        return bytes(retained), overflow, child.poll(), eof
    finally:
        child.stderr.close()


def profile_probe(root):
    require(os.environ.get('GITHUB_EVENT_NAME') == 'push' and
            os.environ.get('GITHUB_REF') == 'refs/heads/feature/iios-provider-gateway-superbatch-1',
            'PROFILE_PROBE_EVENT')
    hosted(); root_check(root)
    environment = json.loads((root/'export/environment.json').read_bytes())
    require_execution_source(environment['source_commit'], os.environ.get('GITHUB_SHA'), os.environ.get('GITHUB_REF'))
    require(command(['/usr/bin/git', 'rev-parse', 'HEAD'], cwd=REPO).decode().strip() == environment['source_commit']
            and command(['/usr/bin/git', 'status', '--porcelain'], cwd=REPO) == b'', 'SOURCE_STATE')
    offline_result = json.loads((root/'export/offline-results.json').read_bytes())
    require(offline_result['success'] is True and not offline_result['skipped'] and
            offline_result['executed'] == offline_result['collected'], 'OFFLINE_REQUIRED')
    verify_bindings(offline_result['source_bindings'])
    runtime = root/'runtime'; interpreter = runtime/'python/bin/python3.13'
    pins = json.loads((root/'export/prepared-pins.json').read_bytes())
    sys.path.insert(0, str(runtime/'source'))
    from alpha_radar_runner import read_descriptor, confinement_profile, descriptor_schema, verify_tools
    from alpha_radar_admission import verify_inputs
    d = read_descriptor(root/'descriptor.json', pins['descriptor_sha256'])
    descriptor_schema(d); verify_inputs(d['package'], d['runtime'], d['expected'], root)
    verify_tools(d['native_tools'])
    require(Path(sys.executable).resolve() == interpreter and
            environment['tools']['/usr/bin/sandbox-exec'] == d['native_tools']['/usr/bin/sandbox-exec'], 'STATIC_IDENTITY')
    require(not any((root/name).exists() for name in
            ('execution-output', 'native-attempt.json', 'confinement-denied-input')), 'ATTEMPT_ALREADY_EXISTS')
    exact = confinement_profile(runtime, root/'execution-output', interpreter, 38493)
    require(exact.encode() == (runtime/'confinement.sb').read_bytes() and
            digest(exact.encode()) == d['expected']['confinement'], 'PROFILE_PROBE_PROFILE')
    probe_root = root/'profile-probes'; probe_root.mkdir(mode=0o700)  # exclusive series marker
    variants = grammar_matrix(exact)
    executable_pin = fixed_probe_executable()
    libraries = command(['/usr/bin/otool', '-L', PROBE_EXECUTABLE]).decode('ascii')
    require(all(line.strip().startswith(('/usr/lib/', '/System/Library/'))
                for line in libraries.splitlines()[1:]), 'DYNAMIC_DEPENDENCY')
    document(root/'export/profile-executable.json', {'executable': executable_pin,
        'library_listing_sha256': digest(libraries.encode()),
        'environment_parent': digest(canonical(environment)),
        'source_commit': environment['source_commit'],
        'original_profile_sha256': digest(exact.encode()),
        'scope': 'SYNTHETIC_PROFILE_DIAGNOSTIC_ONLY'})
    replacements = {PROBE_EXECUTABLE: 'DIAGNOSTIC_EXECUTABLE', str(interpreter): 'INTERPRETER', str(runtime): 'RUNTIME', str(REPO): 'WORKSPACE',
        str(root/'execution-output'): 'OUTPUT', str(root): 'ROOT', '/System/Library': 'SYSTEM_LIBRARY',
        '/usr/lib': 'USR_LIB', '/dev/null': 'DEVICE', '/dev/urandom': 'DEVICE', '/dev/random': 'DEVICE'}
    # This phase's process boundary is installed once, with a finite immutable
    # command allowlist. No supervisor/fixture/worker script occurs in any argv.
    commands = []
    for index, (_, profile) in enumerate(variants):
        path = probe_root/(str(index)+'.sb'); put(path, profile.encode())
        replacements[str(path)] = 'PROFILE'
        commands.append(('/usr/bin/sandbox-exec', '-f', str(path), PROBE_EXECUTABLE))
    admitted = tuple(commands)
    def boundary(event, args):
        if event == 'subprocess.Popen':
            require(len(args) == 4 and tuple(args[1]) in admitted, 'PROFILE_PROBE_SPAWN')
            probe_spawn_audit(tuple(args[1]), probe_root)(event, args)
        else: preparation_audit(event, args)
    sys.addaudithook(boundary)
    results = []
    for index, ((name, profile), argv) in enumerate(zip(variants, commands)):
        # Recheck immutable target bytes immediately before each compiler probe.
        require(digest(Path(argv[2]).read_bytes()) == digest(profile.encode()), 'PROFILE_PROBE_PROFILE')
        verify_tools(d['native_tools'])
        interpreter_row = next(row for row in d['runtime']['files'] if row['path'] == d['runtime']['interpreter'])
        require(digest(interpreter.read_bytes()) == interpreter_row['sha256'], 'STATIC_IDENTITY')
        require(fixed_probe_executable() == executable_pin, 'STATIC_IDENTITY')
        raw, overflow, code, eof = probe_child(list(argv), probe_root)
        sanitized = sanitize_probe_lines(raw, replacements, overflow=overflow)
        del raw
        result = {'scope': 'SYNTHETIC_PROFILE_DIAGNOSTIC_ONLY', 'ordinal': index+1, 'profile': name,
            'profile_sha256': digest(profile.encode()), 'command_shape_sha256': digest(canonical(
                ['sandbox-exec', '-f', '<PROFILE>', '<DIAGNOSTIC_EXECUTABLE>'])),
            'exit_code': code if code is None or code >= 0 else None,
            'returncode': code, 'signal': -code if code is not None and code < 0 else None,
            'classification': classify_probe(sanitized, code, eof, profile),
            'executable_parent': digest((root/'export/profile-executable.json').read_bytes()),
            'eof': eof, 'diagnostic': sanitized, 'raw_stderr_retained': False,
            'root_cause': 'NOT_ESTABLISHED', 'fixture_launches': 0, 'worker_launches': 0,
            'authority': d['package']['authority'], 'environment_parent': digest(canonical(environment)),
            'descriptor_parent': pins['descriptor_sha256'], 'source_commit': environment['source_commit']}
        document(root/'export'/('profile-probe-'+str(index+1).zfill(2)+'.json'), result)
        results.append(result)
        require(code is not None and eof, 'PROFILE_PROBE_TIMEOUT')
        require(sanitized['status'] in ('SANITIZED', 'PARTIALLY_SANITIZED'), 'PROFILE_PROBE_SANITIZATION')
    document(root/'export/profile-probe-summary.json', {'scope': 'SYNTHETIC_PROFILE_DIAGNOSTIC_ONLY',
        'count': len(results), 'maximum': PROBE_LIMIT, 'results': [digest(canonical(r)) for r in results],
        'fixture_series': 'CLOSED_RED_THREE_ATTEMPTS_CONSUMED', 'new_fixture_attempt': False,
        'qualification': 'NOT_ESTABLISHED', 'authority': d['package']['authority']})



def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=('prepare','finalize','offline','execute','export','profile-probe'))
    parser.add_argument('--root',required=True);parser.add_argument('--commit')
    parser.add_argument('--native-startup', action='store_true', default=False)
    args=parser.parse_args();root=Path(args.root)
    try:
        if args.phase not in ('execute', 'profile-probe'):
            require(not args.native_startup, 'NATIVE_EXECUTION_NOT_AUTHORIZED')
            sys.addaudithook(preparation_audit)
        if args.phase == 'profile-probe':
            require(not args.native_startup, 'NATIVE_EXECUTION_NOT_AUTHORIZED')
            profile_probe(root)
        elif args.phase == 'execute': execute(root, native_startup=args.native_startup)
        elif args.phase in ('prepare','finalize'): globals()[args.phase](root,args.commit)
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
