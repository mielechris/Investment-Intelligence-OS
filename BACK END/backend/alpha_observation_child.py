"""Pinned receipt-only observation component, never a market-data worker.

Invoked only by the separate launch owner through mandatory OS confinement.
It cannot consume an offline package as authority to dispatch provider data.
"""
import argparse
import os
from pathlib import Path
import socket
import ssl
import sys
import time

# -I excludes script-directory imports. The launch owner independently pins the
# complete immutable release before admitting this exact script and directory.
if __name__ == '__main__':
    sys.path.insert(0,str(Path(__file__).parent))

from alpha_observation_launch import (SCOPE, ENV, ROLES, lexical, directory, validate_spec)
from alpha_session_contract import require
from alpha_session_execution import publish, read_record, verify_destination
from provider_gateway_contract import content_hash, locked_authority


def load(path, expected, size):
    lexical(path)
    require(type(size) is int and 0<size<=4*1024*1024,'CHILD_DESCRIPTOR_SIZE')
    fd=directory(str(Path(path).parent))
    try:
        require(Path(path).name=='launch.json','CHILD_DESCRIPTOR_NAME')
        spec=read_record(fd,'launch.json',expected_hash=expected)
        from provider_gateway_contract import canonical
        require(len(canonical(spec))==size,'CHILD_DESCRIPTOR_SIZE')
    finally: os.close(fd)
    validate_spec(spec,content_hash(spec),roots=spec['roots'],source=spec['source'],
        topology_parent=spec['topology_parent'],now_ns=time.monotonic_ns())
    require(path==spec['roots']['output']+'/launch.json' and os.getppid()==spec['parent_pid'] and
        os.path.realpath(sys.executable)==spec['interpreter'] and os.getcwd()==spec['roots']['release'],
        'CHILD_BINDING')
    return spec


def wait_record(fd,name,deadline,*,clock=time.monotonic_ns,pause=time.sleep):
    last=clock()
    while True:
        now=clock(); require(last<=now<deadline,'CHILD_DEADLINE'); last=now
        try: return read_record(fd,name)
        except FileNotFoundError: pause(.01)


def run_child(spec,role):
    require(role in ROLES and dict(os.environ)==ENV,'CHILD_ENVIRONMENT')
    parent=content_hash(spec); fd=directory(spec['roots']['output']); listener=None
    try:
        if role=='backend':
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(spec['roots']['control']+'/loopback.crt',spec['roots']['control']+'/loopback.pem')
            listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            listener.bind(('127.0.0.1',spec['port'])); listener.listen(1)
            listener.settimeout(.05)
        verify_destination(fd,spec['roots']['output'])
        startup={'scope':SCOPE,'launch_parent':parent,'role':role,'pid':os.getpid(),
            'parent_pid':os.getppid(),'startup_ns':spec['startup_ns'],'authority':locked_authority()}
        publish(fd,role+'-startup.json',startup)
        ack=wait_record(fd,role+'-ack.json',spec['startup_ns'])
        require(ack.get('schema')=='iios-observation-launch-receipt-v1' and ack.get('scope')==SCOPE and
            ack.get('launch_parent')==parent and ack.get('stage')==role+'-ack' and
            ack.get('authority')==locked_authority() and ack.get('production_qualified') is False and
            ack.get('payload',{}).get('startup_parent')==content_hash(startup) and
            ack['payload'].get('listener_verified') is True,'CHILD_ACK')
        served=False; last=time.monotonic_ns()
        while True:
            now=time.monotonic_ns(); require(last<=now<spec['stop_ns'],'CHILD_STOP_DEADLINE'); last=now
            try:
                stop=read_record(fd,role+'-stop.json'); break
            except FileNotFoundError: pass
            if listener is not None and not served:
                try: peer,address=listener.accept()
                except socket.timeout: continue
                require(address[0]=='127.0.0.1','CHILD_PEER')
                with peer:
                    peer.settimeout(min(2,(spec['stop_ns']-time.monotonic_ns())/1e9))
                    with context.wrap_socket(peer,server_side=True) as tls:
                        tls.sendall(b'OBSERVATION_COMPONENT_ONLY\n')
                served=True
            else: time.sleep(.01)
        require(stop.get('schema')=='iios-observation-launch-receipt-v1' and stop.get('scope')==SCOPE and
            stop.get('launch_parent')==parent and stop.get('stage')==role+'-stop' and
            stop.get('authority')==locked_authority() and stop.get('production_qualified') is False and
            stop.get('payload',{}).get('owner_parent') is not None,'CHILD_STOP')
        if listener is not None: listener.close(); listener=None
        verify_destination(fd,spec['roots']['output'])
        publish(fd,role+'-exit.json',{'scope':SCOPE,'launch_parent':parent,'role':role,
            'pid':os.getpid(),'stop_parent':content_hash(stop),'authority':locked_authority()})
    finally:
        if listener is not None: listener.close()
        os.close(fd)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--descriptor',required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--bytes',required=True,type=int);p.add_argument('--role',required=True,choices=ROLES)
    a=p.parse_args(argv)
    try: run_child(load(a.descriptor,a.sha256,a.bytes),a.role)
    except Exception:
        # No raw exception text, traceback, arbitrary path or child output.
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
