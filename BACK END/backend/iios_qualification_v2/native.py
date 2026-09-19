"""Selected-Mac effects. Every runtime role is a directly owned bounded child."""
from dataclasses import asdict
import http.client
import json
import os
from pathlib import Path
import platform
import re
import select
import socket
import ssl
import stat
import subprocess
import time
import uuid
from .state import AUTHORITY, require, decode, digest, publish, file_hash, historical_exception
from .runtime import command, ENV


def boot():
    value=command(['/usr/sbin/sysctl','-n','kern.bootsessionuuid']).strip().lower()
    require(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',value),'BOOT_UUID')
    return value


def selected_host(path):
    require(platform.system()=='Darwin' and platform.machine()=='arm64','SELECTED_MAC_ONLY')
    st=path.lstat();require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o600,'HOST_SELECTION_MODE')
    host=decode(path.read_bytes())
    if host.get('schema')==4:return local_selected_host(host)
    required={'schema','control_repository','control_repository_id','control_owner_id','control_ref',
              'workflow','source','runner_name','hardware_uuid','uid'}
    require(set(host)==required and host['schema']==3,'HOST_SELECTION_SCHEMA')
    require(set(host['source'])=={'repository','commit','inventory_sha256'},'HOST_SOURCE_SCHEMA')
    require(host['control_repository']=='mielechris/IIOS-Native-Control' and
            host['control_ref']=='refs/heads/main' and host['workflow']=='native-qualification.yml' and
            host['source']['repository']=='mielechris/Investment-Intelligence-OS','HOST_FIXED_SCOPE')
    require(type(host['control_repository_id']) is int and host['control_repository_id']>0 and
            type(host['control_owner_id']) is int and host['control_owner_id']>0 and
            type(host['uid']) is int and re.fullmatch(r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}',host['hardware_uuid']) and
            re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',host['runner_name']),'HOST_VALUE')
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='self-hosted','SELF_HOSTED_JOB_ONLY')
    require(os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch','MANUAL_DISPATCH_ONLY')
    require(os.environ.get('GITHUB_REPOSITORY')==host['control_repository'] and
            os.environ.get('GITHUB_REPOSITORY_ID')==str(host['control_repository_id']) and
            os.environ.get('GITHUB_REPOSITORY_OWNER_ID')==str(host['control_owner_id']) and
            os.environ.get('RUNNER_NAME')==host['runner_name'],'RUNNER_SELECTION')
    require(os.environ.get('GITHUB_WORKFLOW_REF')==host['control_repository']+'/.github/workflows/'+host['workflow']+'@'+host['control_ref'],'TRUSTED_WORKFLOW_REF')
    require(os.environ.get('GITHUB_REF')==host['control_ref'] and os.environ.get('GITHUB_REF_TYPE')=='branch' and
            not os.environ.get('GITHUB_HEAD_REF') and not os.environ.get('GITHUB_BASE_REF') and
            host['uid']==os.getuid(),'TRUSTED_REF_ACCOUNT')
    raw=command(['/usr/sbin/ioreg','-rd1','-c','IOPlatformExpertDevice'])
    matches=re.findall(r'"IOPlatformUUID"\s*=\s*"([A-Fa-f0-9-]+)"',raw)
    require(len(matches)==1 and matches[0].lower()==host['hardware_uuid'].lower(),'SELECTED_HARDWARE')
    return (dict(control_repository=host['control_repository'],control_ref=host['control_ref'],
                 workflow=host['workflow'],manual_dispatch=True,environment='iios-native-qualification',
                 selected_host_verified=True,hardware_verified=True,runner_verified=True), host['source'])


def local_selected_host(host):
    """Admit only the fixed, signed foreground app that directly owns this process."""
    required={'schema','launch_mode','repository','commit','branch','inventory_sha256','app_bundle',
              'app_executable','app_executable_sha256','app_identifier','app_cdhash','signing_method',
              'app_manifest','app_manifest_sha256','hardware_uuid','uid'}
    require(set(host)==required and host['schema']==4 and host['launch_mode']=='local_app',
            'LOCAL_HOST_SCHEMA')
    home=Path.home();bundle=home/'Applications/IIOS Native Qualification.app'
    executable=bundle/'Contents/MacOS/IIOSNativeQualification'
    manifest=Path(host.get('app_manifest',''))
    require(host['repository']=='mielechris/Investment-Intelligence-OS' and
            host['branch']=='feature/iios-native-qualification-v2' and
            host['app_bundle']==str(bundle) and host['app_executable']==str(executable) and
            host['app_identifier']=='com.miele.iios-native-qualification' and
            manifest.is_absolute() and manifest.name=='APP-MANIFEST.json' and manifest.parent.parent==Path.home()/'Library/IIOS/qualification' and
            host['signing_method']=='adhoc','LOCAL_HOST_SCOPE')
    require(type(host['uid']) is int and host['uid']==os.getuid() and
            re.fullmatch(r'[0-9a-f]{40}',host['commit']) and
            re.fullmatch(r'[0-9a-f]{64}',host['inventory_sha256']) and
            re.fullmatch(r'[0-9a-f]{64}',host['app_executable_sha256']) and
            re.fullmatch(r'[0-9a-f]{64}',host['app_manifest_sha256']) and
            re.fullmatch(r'[0-9A-Fa-f]{40}',host['app_cdhash']) and
            re.fullmatch(r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}',host['hardware_uuid']),
            'LOCAL_HOST_VALUE')
    for item,mode in ((bundle,0o700),(bundle/'Contents',0o700),(bundle/'Contents/MacOS',0o700),(executable,0o700)):
        st=item.lstat();require(not stat.S_ISLNK(st.st_mode) and st.st_uid==os.getuid() and
                               stat.S_IMODE(st.st_mode)==mode,'LOCAL_APP_OWNER_MODE')
    require(file_hash(executable)==host['app_executable_sha256'],'LOCAL_APP_EXECUTABLE_HASH')
    st=manifest.lstat();require(stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode) and st.st_uid==os.getuid() and
                                stat.S_IMODE(st.st_mode)==0o400 and file_hash(manifest)==host['app_manifest_sha256'],'LOCAL_APP_MANIFEST_HASH')
    result=subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict','--all-architectures',str(bundle)],
                          env=ENV,stdin=subprocess.DEVNULL,capture_output=True,timeout=10,close_fds=True)
    require(result.returncode==0 and len(result.stdout)+len(result.stderr)<=65536,'LOCAL_APP_SIGNATURE')
    result=subprocess.run(['/usr/bin/codesign','-d','--verbose=4',str(bundle)],env=ENV,
                          stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=10,close_fds=True)
    require(result.returncode==0 and len(result.stdout)+len(result.stderr)<=65536,'LOCAL_APP_SIGNATURE_INFO')
    description=result.stdout+result.stderr
    identifiers=re.findall(r'^Identifier=(.+)$',description,re.M);hashes=re.findall(r'^CDHash=([0-9A-Fa-f]+)$',description,re.M)
    require(identifiers==[host['app_identifier']] and len(hashes)==1 and
            hashes[0].lower()==host['app_cdhash'].lower() and
            ('Signature=adhoc' in description or 'flags=0x2(adhoc' in description),
            'LOCAL_APP_SIGNATURE_BINDING')
    from truth_spine_process_identity import inspect_macos
    parent=inspect_macos(os.getppid())
    require(parent is not None and parent.executable==str(executable) and
            parent.executable_hash==host['app_executable_sha256'],'LOCAL_APP_PARENT')
    raw=command(['/usr/sbin/ioreg','-rd1','-c','IOPlatformExpertDevice'])
    matches=re.findall(r'"IOPlatformUUID"\s*=\s*"([A-Fa-f0-9-]+)"',raw)
    require(len(matches)==1 and matches[0].lower()==host['hardware_uuid'].lower(),'SELECTED_HARDWARE')
    issuer=dict(launch_mode='local_app',application=host['app_identifier'],signing_method='adhoc',
                selected_host_verified=True,hardware_verified=True,parent_verified=True,
                hardware_uuid=matches[0].lower(),app_executable_sha256=host['app_executable_sha256'],
                app_manifest_sha256=host['app_manifest_sha256'])
    expected=dict(repository=host['repository'],commit=host['commit'],branch=host['branch'],
                  inventory_sha256=host['inventory_sha256'])
    return issuer,expected


def profile(source, runtime, work, python, port, denied=None):
    literal=lambda value:json.dumps(str(value))
    roots=[source,runtime,work,Path('/Library/Frameworks/Python.framework/Versions/3.14'),Path('/System/Library'),Path('/usr/lib'),Path('/usr/share')]
    lines=['(version 1)','(allow default)','(deny network*)',
           '(allow network-inbound (local ip "127.0.0.1:'+str(port)+'"))',
           '(allow network-outbound (remote ip "127.0.0.1:'+str(port)+'"))',
           '(deny file-read-data)','(allow file-read-metadata)','(allow file-read-data (literal "/") (literal "/dev/null") (literal "/dev/urandom"))',
           '(allow file-read-data '+ ' '.join('(subpath '+literal(p)+')' for p in roots)+')',
           '(deny file-write*)','(allow file-write* (subpath '+literal(work)+'))',
           '(deny process-fork)','(deny process-exec)','(allow process-exec (literal '+literal(python)+') (literal "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14") (literal "/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python"))']
    for root in (Path.home()/'.ssh',Path.home()/'.aws',Path.home()/'Library/Keychains',Path('/Library/Keychains'),Path('/System/Library/Keychains')):
        lines.append('(deny file-read* (subpath '+literal(root)+'))')
    if denied:lines.append('(deny file-read-data (literal '+literal(denied)+'))')
    return '\n'.join(lines)+'\n'


class Native:
    def __init__(self, source, work, store, runtime, current_boot, deadline):
        self.source=Path(source);self.work=Path(work);self.store=store;self.runtime=runtime
        self.boot=current_boot;self.deadline=deadline;self.children=[];self.receipts=[]
        from truth_spine_process_identity import inspect_macos
        self.inspect=inspect_macos

    def check(self):require(time.monotonic()<self.deadline and boot()==self.boot,'NATIVE_DEADLINE_OR_BOOT')

    def line(self, child, seconds=15):
        end=min(self.deadline,time.monotonic()+seconds);raw=b''
        while time.monotonic()<end:
            if select.select([child.stdout],[],[],max(0,end-time.monotonic()))[0]:
                chunk=os.read(child.stdout.fileno(),1)
                require(chunk,'CHILD_EOF');raw+=chunk
                require(len(raw)<=65536,'CHILD_OUTPUT_BOUND')
                if chunk==b'\n':return decode(raw)
        raise TimeoutError('CHILD_ACK_DEADLINE')

    def identity(self, child, argv):
        rows=[self.inspect(child.pid) for _ in range(3)]
        require(rows[0] is not None and rows==[rows[0]]*3,'OWNERSHIP_STABILITY')
        row=rows[0];vendor=self.runtime['manifest']['vendor']
        require(row.pid==child.pid and row.parent_pid==os.getpid() and bool(row.start_time),'OWNERSHIP_PID_PARENT_START')
        require(row.executable==vendor['image'] and row.executable_hash==vendor['image_sha256'],'OWNERSHIP_IMAGE')
        require(row.cwd==str(self.work) and tuple(row.argv[1:])==tuple(argv[1:]) and row.argv[0] in (argv[0],vendor['image']),'OWNERSHIP_ARGV_CWD')
        return row

    def launch(self, role, *, confined=True, operation=None, target=None, target_port=None, port=38493, session=None):
        self.check();nonce=uuid.uuid4().hex
        config=dict(role=role,nonce=nonce,work=str(self.work),authority=AUTHORITY,session=session or nonce,
                    port=port,certificate=str(self.work/'loopback.crt'),key=str(self.work/'loopback.key'))
        if operation:config.update(operation=operation,target=str(target) if target else None,target_port=target_port)
        path=self.work/(role+'-'+nonce+'.json');publish(path,config)
        python=str(Path(self.runtime['path'])/'bin/python');script=self.source/'BACK END/backend/iios_qualification_v2/child.py'
        argv=[python,'-I','-B','-S',str(script),str(path)];launch=argv
        if confined:
            policy=self.work/(nonce+'.sb');policy.write_text(profile(self.source,Path(self.runtime['path']),self.work,python,port,target));policy.chmod(0o400)
            launch=['/usr/bin/sandbox-exec','-f',str(policy)]+argv
        self.store.append('LAUNCH_INTENT',dict(boot=self.boot,nonce=nonce,role=role))
        child=subprocess.Popen(launch,cwd=self.work,env=ENV,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,close_fds=True)
        entry=dict(child=child,identity=None,config=config,argv=argv);self.children.append(entry)
        self.store.append('CHILD_LAUNCHED',dict(pid=child.pid,boot=self.boot,nonce=nonce,role=role))
        ready=self.line(child);require(ready.get('event')=='READY' and ready.get('pid')==child.pid,'STARTUP_READY')
        row=self.identity(child,argv);entry['identity']=row
        self.store.append('CHILD_OWNED',dict(identity=asdict(row),boot=self.boot,nonce=nonce))
        for k,v in dict(nonce=nonce,role=role,config_parent=digest(config),authority=AUTHORITY).items():require(ready.get(k)==v,'STARTUP_BINDING')
        child.stdin.write(('ACK '+nonce+'\n').encode());child.stdin.flush()
        result=self.line(child)
        for k,v in dict(event='DATA',nonce=nonce,role=role,config_parent=digest(config),authority=AUTHORITY).items():require(result.get(k)==v,'ACK_RESULT_BINDING')
        entry['result']=result
        return entry

    def stop(self, entry):
        child=entry['child'];nonce=entry['config']['nonce']
        # Never signal an inspected PID recovered from a prior controller. This is a held child handle.
        child.stdin.write(('STOP '+nonce+'\n').encode());child.stdin.flush()
        stopped=self.line(child,10)
        require(stopped.get('event')=='STOPPED' and stopped.get('nonce')==nonce,'STOP_ACK')
        for origin in stopped['origins'].values():
            p=Path(origin['path'])
            require(p.is_file() and file_hash(p)==origin['sha256'],'MODULE_HASH')
            require(p.is_relative_to(self.source) or p.is_relative_to(Path(self.runtime['path'])) or str(p).startswith('/Library/Frameworks/Python.framework/Versions/3.14/'),'MODULE_ORIGIN')
        require(child.wait(timeout=10)==0,'CHILD_EXIT')
        require(all(self.inspect(child.pid) is None for _ in range(3)),'CHILD_ABSENCE')
        self.store.append('CHILD_REAPED',dict(pid=child.pid,boot=self.boot,nonce=nonce,exit=0,absence_samples=3))
        self.children.remove(entry)
        return dict(pid=child.pid,exit=0,absence_samples=3,origins=stopped['origins'])

    def cleanup(self):
        failures=[]
        for entry in list(reversed(self.children)):
            try:self.stop(entry)
            except Exception:
                child=entry['child']
                try:
                    # Identity failure does not authorize a signal; the child's self-alarm is independent.
                    if entry['identity'] is not None and self.inspect(child.pid)==entry['identity']:
                        child.terminate()
                    child.wait(timeout=15)
                    require(all(self.inspect(child.pid) is None for _ in range(3)),'CLEANUP_ABSENCE')
                    self.store.append('CHILD_REAPED',dict(pid=child.pid,boot=self.boot,nonce=entry['config']['nonce'],exit=child.returncode,absence_samples=3))
                    self.children.remove(entry)
                    failures.append('NONCOOPERATIVE_CLEANUP')
                except Exception:failures.append('CLEANUP_NOT_ESTABLISHED')
        require(not failures and not self.children,'CLEANUP_FAILED:'+','.join(failures))
        return dict(cooperative=True,outstanding=0,verified=True)

    def ownership(self):
        entry=self.launch('probe',confined=False,operation='identity')
        return dict(observation=asdict(entry['identity']),cleanup=self.stop(entry))

    def confinement(self):
        results=[]
        for kind in ('filesystem','credential_boundary','network','subprocess'):
            target=self.work/(uuid.uuid4().hex+'-canary');target.write_bytes(b'IIOS_SYNTHETIC_CANARY\n');target.chmod(0o600)
            with socket.socket() as listener:
                listener.bind(('127.0.0.1',0));listener.listen();port=listener.getsockname()[1]
                allowed=self.launch('probe',confined=False,operation=kind,target=target,target_port=port)
                require(allowed['result']['outcome']=='ALLOWED','CONTROLLED_BASELINE')
                self.stop(allowed)
                denied=self.launch('probe',confined=True,operation=kind,target=target,target_port=port)
                require(denied['result']['outcome']=='DENIED' and denied['result']['errno'] in (1,13),'CONTROLLED_DENIAL')
                pid=denied['child'].pid
                require(self.inspect(pid)==denied['identity'],'DENIAL_OWNER_STABLE')
                predicate='eventMessage CONTAINS "('+str(pid)+')" AND eventMessage CONTAINS "deny"'
                logs=command(['/usr/bin/log','show','--last','2m','--style','compact','--predicate',predicate],timeout=20)
                operation={'network':'network-outbound','subprocess':'process-exec'}.get(kind,'file-read-data')
                expected='/usr/bin/true' if kind=='subprocess' else ('127.0.0.1:'+str(port) if kind=='network' else str(target))
                matches=[line for line in logs.splitlines() if 'Sandbox:' in line and '('+str(pid)+')' in line and operation in line and expected in line]
                require(matches,'OS_DENIAL_ATTRIBUTION_UNAVAILABLE')
                results.append(dict(kind=kind,baseline='ALLOWED',confined='DENIED',owner=asdict(denied['identity']),os_evidence=matches,cleanup=self.stop(denied)))
        return results

    def startup(self):
        config=self.work/'tls.cnf';config.write_text('[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=v3\n[dn]\nCN=IIOS synthetic loopback\n[v3]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\nsubjectAltName=IP:127.0.0.1\n')
        command(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-config',config,
                 '-keyout',self.work/'loopback.key','-out',self.work/'loopback.crt'],timeout=30)
        (self.work/'loopback.key').chmod(0o400)
        with socket.socket() as probe:probe.bind(('127.0.0.1',0));self.port=probe.getsockname()[1]
        scheduler=self.launch('scheduler',port=self.port);self.session=scheduler['config']['nonce']
        publisher=self.launch('publisher',port=self.port,session=self.session)
        backend=self.launch('backend',port=self.port,session=self.session)
        self.roles=[scheduler,publisher,backend]
        listeners=command(['/usr/sbin/lsof','-nP','-iTCP:'+str(self.port),'-sTCP:LISTEN','-Fp'])
        require({int(x[1:]) for x in listeners.splitlines() if x.startswith('p')}=={backend['child'].pid},'LISTENER_OWNERSHIP')
        return [dict(role=e['config']['role'],identity=asdict(e['identity']),ack=e['result']) for e in self.roles]

    def tls(self):
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);ctx.load_verify_locations(cafile=str(self.work/'loopback.crt'))
        rows=[]
        for method in ('GET','HEAD'):
            connection=http.client.HTTPSConnection('127.0.0.1',self.port,context=ctx,timeout=5)
            try:
                connection.request(method,'/health');response=connection.getresponse();body=response.read(65537)
                require(response.status==200 and len(body)<=65536,'LOOPBACK_TLS_RESPONSE')
                if method=='GET':self.projection=decode(body)
                else:require(not body,'HEAD_BODY')
                rows.append(dict(method=method,status=response.status,tls_verified=True))
            finally:connection.close()
        return dict(requests=rows,certificate_sha256=file_hash(self.work/'loopback.crt'),provider_requests=0)

    def truth_spine(self):
        from truth_spine_contract import verified
        from truth_spine_observation_roles import seed
        from provider_gateway_contract import content_hash
        ledger=verified(decode((self.work/'seeded-ledger.json').read_bytes()));projection=verified(self.projection)
        require(projection==verified(decode((self.work/'projection.json').read_bytes())),'HTTP_PROJECTION_PARENT')
        require(projection['parent']==ledger['content_hash'] and projection['session']==self.session,'TRUTH_SPINE_LINEAGE')
        previous=None
        require(len(ledger['records'])==3 and projection['seeded_records']==3 and projection['executed_requests']==0,'TRUTH_SPINE_COUNTS')
        for index,row in enumerate(ledger['records']):require(row==seed(index,previous),'TRUTH_SPINE_SEED');previous=content_hash(row)
        require(projection['authority']==AUTHORITY,'AUTHORITY')
        return dict(roles=['scheduler','publisher','backend'],ledger_parent=ledger['content_hash'],projection_parent=projection['content_hash'],seeded_records=3,executed_requests=0,provider_requests=0)


def reconcile(records, current_boot, inspect):
    outstanding={}
    for row in records:
        data=row['data']
        if row['event'] in ('LAUNCH_INTENT','CHILD_LAUNCHED'):outstanding[data['nonce']]=data
        if row['event']=='CHILD_REAPED':outstanding.pop(data['nonce'],None)
    result=[]
    for value in outstanding.values():
        if value['boot']!=current_boot:
            result.append(dict(**value,disposition='PRIOR_BOOT_EXCEPTION',historical_cleanup='NOT_ESTABLISHED'))
        else:
            require('pid' in value,'CURRENT_BOOT_LAUNCH_INTENT_UNRESOLVED')
            require(all(inspect(value['pid']) is None for _ in range(3)),'CURRENT_BOOT_CHILD_UNRESOLVED')
            result.append(dict(**value,disposition='CURRENT_ABSENCE_THREE_OBSERVATIONS',historical_cleanup='NOT_ESTABLISHED'))
    return result
