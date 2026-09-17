"""Explicit receipt-only launch binding. Never admits provider execution.

Independent invocation pins authorize component effects only. The shadow service,
production CLI and account/transport admission remain separate and unchanged.
No command, environment, retry or unconstrained path is supplied by a child.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import os
from pathlib import PurePosixPath
import re
import socket
import ssl
import stat
import subprocess
import time

from alpha_session_contract import require
from alpha_session_evidence import path_parts, verify_files
from alpha_session_execution import publish, read_record, verify_destination
from provider_gateway_contract import content_hash, locked_authority, pin, safe_document
from truth_spine_process_identity import ProcessObservation, inspect_macos, utc_stamp
from truth_spine_session_supervisor import ROLES

SCOPE = 'OBSERVATION_LAUNCH_COMPONENT_ONLY'
ENV = {'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC'}
CHILD = 'alpha_observation_child.py'
STREAM_LIMIT = 4096


def lexical(path):
    parts = path_parts(path, absolute=True)
    require(not any(p.lower() in {'keychains', 'ledger', 'ledgers', 'l7', 'l8', '.ssh', '.aws',
        '.env', 'application support'} or p.startswith('~') for p in parts), 'LAUNCH_PATH')
    return PurePosixPath(path)


def validate_spec(spec, expected, *, roots, source, topology_parent, now_ns):
    """Pure admission first. Roots and digest come from the independent reviewer.

    A component capability is not an account, OS-confinement, or production proof.
    Sandbox application remains mandatory on every child command.
    """
    from alpha_runtime_files import safe_runtime_envelope
    safe_runtime_envelope(spec); pin(spec, expected)
    from alpha_runtime_files import EXTENSION_FIELDS, extension
    version2 = spec.get('schema') == 'iios-observation-launch-v2'
    if version2: extension(spec)
    require(set(spec) == ({'schema','scope','source','topology_parent','roots','inventories','interpreter',
        'interpreter_hash','sandbox_hash','host','port','peer_hash','parent_pid','start_ns','startup_ns',
        'stop_ns','final_ns','authority'} | (EXTENSION_FIELDS if version2 else set())), 'LAUNCH_SCHEMA')
    require(spec['schema'] in ('iios-observation-launch-v1','iios-observation-launch-v2') and spec['scope'] == SCOPE and
            re.fullmatch('[0-9a-f]{40}', source) and spec['source'] == source and
            spec['topology_parent'] == topology_parent and re.fullmatch('[0-9a-f]{64}', topology_parent), 'LAUNCH_PARENT')
    require(type(roots) is dict and set(roots) == {'runtime','release','control','output'} and
            spec['roots'] == roots, 'LAUNCH_ROOTS')
    paths = [lexical(roots[k]) for k in roots]
    require(all(not a.is_relative_to(b) and not b.is_relative_to(a)
                for i,a in enumerate(paths) for b in paths[i+1:]), 'LAUNCH_ROOT_OVERLAP')
    require(spec['authority'] == locked_authority() and all(v is False for v in spec['authority'].values()), 'LAUNCH_AUTHORITY')
    require(spec['host'] == '127.0.0.1' and type(spec['port']) is int and 1024 <= spec['port'] <= 65535,
            'LAUNCH_ENDPOINT')
    require(type(spec['parent_pid']) is int and spec['parent_pid'] > 0, 'LAUNCH_PARENT_PID')
    for k in ('start_ns','startup_ns','stop_ns','final_ns'):
        require(type(spec[k]) is int and 0 < spec[k] < 2**63, 'LAUNCH_CLOCK')
    require(spec['start_ns'] <= now_ns < spec['startup_ns'] < spec['stop_ns'] < spec['final_ns'] and
            spec['startup_ns']-spec['start_ns'] <= 120_000_000_000 and
            spec['final_ns']-spec['start_ns'] <= 900_000_000_000 and
            spec['final_ns']-spec['stop_ns'] >= 120_000_000_000, 'LAUNCH_BUDGET')
    require(set(spec['inventories']) == {'runtime','release','control'}, 'LAUNCH_INVENTORY')
    for k in ('interpreter_hash','sandbox_hash','peer_hash'):
        require(type(spec[k]) is str and re.fullmatch('[a-f0-9]{64}', spec[k]), 'LAUNCH_HASH')
    require(spec['interpreter'] == roots['runtime']+'/bin/python3.14', 'LAUNCH_INTERPRETER')
    for role,name,expected_hash in [('runtime','bin/python3.14',spec['interpreter_hash']),
                                    ('release',CHILD,None),('control','profile.sb',None),
                                    ('control','loopback.crt',None),('control','loopback.pem',None)]:
        rows = [r for r in spec['inventories'][role] if r.get('path') == name]
        require(len(rows)==1 and (expected_hash is None or rows[0]['sha256']==expected_hash), 'LAUNCH_REQUIRED_FILE')
    return deepcopy(spec)


def verify_inputs(spec):
    for role in ('runtime','release','control'):
        if role == 'runtime' and spec['schema'] == 'iios-observation-launch-v2':
            from alpha_runtime_files import verify_runtime_tree, extension
            verify_runtime_tree(spec['roots'][role],spec['inventories'][role],approved_root=spec['roots'][role],**extension(spec))
        else:
            verify_files(spec['roots'][role], spec['inventories'][role], approved_root=spec['roots'][role])
    # This fixed system launcher is never replaced by a caller-supplied executable.
    with open('/usr/bin/sandbox-exec','rb') as stream:
        require(hashlib.sha256(stream.read(4*1024*1024)).hexdigest()==spec['sandbox_hash'], 'LAUNCH_SANDBOX_IDENTITY')


def directory(path):
    parts = lexical(path).parts[1:]
    fd = os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in parts:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd); fd=child
        st=os.fstat(fd)
        require(st.st_uid==os.getuid() and not st.st_mode&0o077, 'LAUNCH_DIRECTORY')
        return fd
    except BaseException:
        os.close(fd); raise


def command(spec, role, descriptor_hash, descriptor_size):
    require(role in ROLES, 'LAUNCH_ROLE')
    return [spec['interpreter'],'-I','-B',spec['roots']['release']+'/'+CHILD,
        '--descriptor',spec['roots']['output']+'/launch.json','--sha256',descriptor_hash,
        '--bytes',str(descriptor_size),'--role',role]


def observed(value):
    require(type(value) is ProcessObservation, 'LAUNCH_INSPECTION')
    row=asdict(value); row['argv']=list(row['argv'])
    return row


def listener_pids(port):
    result=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:'+str(port),'-sTCP:LISTEN','-Fp'],
        env=ENV,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=2,check=False)
    require(len(result.stdout)<=4096 and not result.stderr and result.returncode in (0,1), 'LAUNCH_LISTENER_INSPECTION')
    require(all(re.fullmatch(rb'p[1-9][0-9]*',v) for v in result.stdout.splitlines()), 'LAUNCH_LISTENER_FORMAT')
    pids=[int(v[1:]) for v in result.stdout.splitlines()]
    require((result.returncode==1 and not pids) or (result.returncode==0 and bool(pids)), 'LAUNCH_LISTENER_STATUS')
    return pids


class LaunchOwner:
    """One-shot parent effect owner; independent cleanup for every created role.

    All child output is bounded in memory and reduced to a fixed category/count.
    Native tests must establish sandbox, process inspection and TLS semantics.
    """
    def __init__(self,spec,expected,*,roots,source,topology_parent):
        self.spec=validate_spec(spec,expected,roots=roots,source=source,
            topology_parent=topology_parent,now_ns=time.monotonic_ns())
        require(os.getpid()==spec['parent_pid'], 'LAUNCH_SUPERVISOR_PID')
        self.parent=expected; self.children={}; self.owners={}; self.cleanup_results={}
        self.failure=None; self.stage='ADMISSION'; self.fd=None; self.last_ns=spec['start_ns']; self.tls=False
        self.descriptor_hash=None; self.descriptor_size=None; self.acks={}

    def clock(self,deadline):
        now=time.monotonic_ns()
        require(self.last_ns<=now<deadline,'LAUNCH_DEADLINE'); self.last_ns=now
        return now

    def evidence(self,stage,payload):
        require(self.fd is not None,'LAUNCH_OUTPUT_ABSENT')
        verify_destination(self.fd,self.spec['roots']['output'])
        return publish(self.fd,stage+'.json',{'schema':'iios-observation-launch-receipt-v1',
            'scope':SCOPE,'launch_parent':self.parent,'stage':stage,'payload':payload,
            'authority':locked_authority(),'production_qualified':False,'provider_requests':0})

    def prepare(self):
        self.clock(self.spec['startup_ns']); verify_inputs(self.spec)
        require(listener_pids(self.spec['port'])==[], 'LAUNCH_PORT_OCCUPIED')
        root=self.spec['roots']['output']; parent=directory(str(lexical(root).parent))
        try:
            os.mkdir(lexical(root).name,0o700,dir_fd=parent)
            self.fd=os.open(lexical(root).name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
        finally: os.close(parent)
        from provider_gateway_contract import canonical
        self.descriptor_hash=publish(self.fd,'launch.json',self.spec)
        self.descriptor_size=len(canonical(self.spec))

    def drain(self,role):
        child=self.children[role]; counts=child['counts']
        for name in ('stdout','stderr'):
            stream=getattr(child['process'],name)
            while True:
                try: data=os.read(stream.fileno(),min(1024,STREAM_LIMIT-counts[name]+1))
                except BlockingIOError: break
                if not data: break
                counts[name]+=len(data)
                # Never persist arbitrary output, even if it resembles a diagnostic.
                require(counts[name]<=STREAM_LIMIT, 'LAUNCH_OUTPUT_OVERFLOW')
                raise ValueError('LAUNCH_UNEXPECTED_OUTPUT')

    def sample(self,role):
        child=self.children[role]['process']; self.drain(role)
        require(child.poll() is None, 'LAUNCH_CHILD_EXITED')
        return inspect_macos(child.pid)

    def register(self,role):
        self.clock(self.spec['startup_ns']); verify_inputs(self.spec)
        samples=[self.sample(role) for _ in range(3)]
        self.clock(self.spec['startup_ns'])
        baseline=observed(samples[0]); expected=command(self.spec,role,self.descriptor_hash,self.descriptor_size)
        require(all(observed(s)==baseline for s in samples),'LAUNCH_UNSTABLE_IDENTITY')
        require(baseline['pid']==self.children[role]['process'].pid and
            baseline['parent_pid']==self.spec['parent_pid'] and baseline['argv']==expected and
            baseline['command']==' '.join(expected) and baseline['cwd']==self.spec['roots']['release'] and
            baseline['executable']==self.spec['interpreter'] and
            baseline['executable_hash']==self.spec['interpreter_hash'] and
            utc_stamp(baseline['start_time'])==baseline['start_time'],'LAUNCH_IDENTITY')
        require(all(o['pid']!=baseline['pid'] for o in self.owners.values()),'LAUNCH_PID_REUSE')
        # Register identity before publication so publication failure cannot lose ownership.
        self.owners[role]=baseline
        return self.evidence(role+'-ownership',{'samples':3,'identity_parent':content_hash(baseline)})

    def startup(self):
        require(self.fd is not None and not self.children,'LAUNCH_DUPLICATE_START')
        for role in ROLES:
            self.clock(self.spec['startup_ns']); verify_inputs(self.spec)
            argv=command(self.spec,role,self.descriptor_hash,self.descriptor_size)
            self.stage='PROCESS_CREATE'
            p=subprocess.Popen(['/usr/bin/sandbox-exec','-f',self.spec['roots']['control']+'/profile.sb',*argv],
                cwd=self.spec['roots']['release'],env=dict(ENV),stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,start_new_session=False)
            self.children[role]={'process':p,'counts':{'stdout':0,'stderr':0}}
            p.stdin.close()
            os.set_blocking(p.stdout.fileno(),False); os.set_blocking(p.stderr.fileno(),False)
            # Startup is published before the child waits for ACK. Waiting here
            # avoids inspecting the transient sandbox-exec wrapper as the child.
            while True:
                self.clock(self.spec['startup_ns']); self.drain(role)
                require(p.poll() is None,'LAUNCH_EARLY_EXIT')
                try: ready=read_record(self.fd,role+'-startup.json'); break
                except FileNotFoundError: time.sleep(.01)
            require(ready=={'scope':SCOPE,'launch_parent':self.parent,'role':role,'pid':p.pid,
                'parent_pid':self.spec['parent_pid'],'startup_ns':self.spec['startup_ns'],
                'authority':locked_authority()},'LAUNCH_STARTUP_RECEIPT')
            self.stage='OWNERSHIP_REGISTER'
            owner_parent=self.register(role)
            self.reverify(role)
            expected_listeners=[self.children['backend']['process'].pid] if role=='backend' else []
            require(listener_pids(self.spec['port'])==expected_listeners,'LAUNCH_LISTENER_OWNER')
            self.clock(self.spec['startup_ns'])
            self.stage='ACK_PUBLICATION'
            self.acks[role]=self.evidence(role+'-ack',{'ownership_parent':owner_parent,
                'startup_parent':content_hash(ready),'listener_verified':True})
        self.clock(self.spec['startup_ns'])
        self.stage='LOOPBACK_TLS'
        context=ssl.create_default_context(cafile=self.spec['roots']['control']+'/loopback.crt')
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as raw:
            raw.settimeout(min(2,(self.spec['startup_ns']-time.monotonic_ns())/1e9))
            raw.connect((self.spec['host'],self.spec['port']))
            with context.wrap_socket(raw,server_hostname='127.0.0.1') as channel:
                require(hashlib.sha256(channel.getpeercert(binary_form=True)).hexdigest()==self.spec['peer_hash'],'LAUNCH_TLS_PIN')
                response=b''
                while len(response)<len(b'OBSERVATION_COMPONENT_ONLY\n'):
                    block=channel.recv(len(b'OBSERVATION_COMPONENT_ONLY\n')-len(response))
                    require(bool(block),'LAUNCH_TLS_RESPONSE'); response+=block
                require(response==b'OBSERVATION_COMPONENT_ONLY\n','LAUNCH_TLS_RESPONSE')
        self.clock(self.spec['startup_ns']); self.tls=True
        return self.evidence('tls',{'peer_parent':self.spec['peer_hash'],'verified':True})

    def reverify(self,role):
        require(role in self.owners,'LAUNCH_UNVERIFIED_CHILD')
        require(observed(self.sample(role))==self.owners[role],'LAUNCH_IDENTITY_CHANGED')

    def cleanup(self):
        # No signal fallback. A child must exit cooperatively after a pinned stop
        # receipt or its own descriptor deadline; unresolved ownership stays RED.
        for role in reversed(ROLES):
            if role not in self.children: continue
            try:
                self.clock(self.spec['final_ns']); self.reverify(role)
                stop_parent=self.evidence(role+'-stop',{'owner_parent':content_hash(self.owners[role])})
                p=self.children[role]['process']
                p.wait(timeout=min(30,max(0,(self.spec['final_ns']-time.monotonic_ns())/1e9)))
                self.drain(role)
                exit_doc=read_record(self.fd,role+'-exit.json')
                require(p.returncode==0 and exit_doc=={'scope':SCOPE,'launch_parent':self.parent,
                    'role':role,'pid':p.pid,'stop_parent':stop_parent,'authority':locked_authority()},'LAUNCH_EXIT')
                self.cleanup_results[role]='COOPERATIVE_VERIFIED'
            except Exception:
                self.cleanup_results[role]='UNVERIFIED'
            finally:
                p=self.children[role]['process']
                for name in ('stdin','stdout','stderr'):
                    try: getattr(p,name).close()
                    except Exception: pass
        clear=[]
        try:
            for _ in range(3):
                self.clock(self.spec['final_ns'])
                require(listener_pids(self.spec['port'])==[],'LAUNCH_LISTENER_SURVIVES')
                with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
                    probe.settimeout(1)
                    import errno
                    require(probe.connect_ex((self.spec['host'],self.spec['port']))==errno.ECONNREFUSED,'LAUNCH_PORT_UNVERIFIED')
                clear.append(True); time.sleep(.05)
        except Exception: clear.append(False)
        success=(set(self.cleanup_results)==set(ROLES) and
            all(v=='COOPERATIVE_VERIFIED' for v in self.cleanup_results.values()) and clear==[True]*3)
        return {'roles':dict(self.cleanup_results),'port_samples':clear,'verified':success}

    def child_results(self):
        return {role:{'pid':row['process'].pid,'returncode':row['process'].poll(),
                      'output_bytes':dict(row['counts']),'ownership_registered':role in self.owners}
                for role,row in self.children.items()}

    def run(self):
        cleanup=None
        try:
            self.stage='PREPARE'
            self.prepare(); self.startup()
        except Exception:
            self.failure='STARTUP_FAILED'
        finally:
            if self.fd is not None:
                cleanup=self.cleanup()
                try:
                    self.evidence('final',{'primary_failure':self.failure,'cleanup':cleanup,
                        'failure_stage':self.stage,'children':self.child_results(),
                        'tls_verified':self.tls,'component_complete':self.failure is None and cleanup['verified']})
                finally: os.close(self.fd); self.fd=None
        return {'scope':SCOPE,'primary_failure':self.failure,'cleanup':cleanup,
                'tls_verified':self.tls,'production_qualified':False,'authority':locked_authority()}
