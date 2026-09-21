"""Fixed synthetic roles and controlled dummy probes; no provider imports or secrets."""
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

sys.dont_write_bytecode = True
# -I -S prevents ambient site hooks; only this reviewed source tree is added.
sys.path.append(str(Path(__file__).resolve().parents[1]))
from iios_qualification_v2.state import AUTHORITY, decode, require, digest, publish, file_hash


def send(config, event, **data):
    print(json.dumps(dict(event=event, nonce=config['nonce'], role=config['role'],
                          config_parent=digest(config), authority=AUTHORITY, **data)), flush=True)


def main():
    config = decode(Path(sys.argv[1]).read_bytes())
    require(config['authority']==AUTHORITY and all(v is False for v in config['authority'].values()), 'AUTHORITY')
    send(config, 'READY', pid=os.getpid())
    require(sys.stdin.readline().strip()=='ACK '+config['nonce'], 'ACK')
    work = Path(config['work'])
    if config['role']=='probe':
        import socket
        import subprocess
        operation = config['operation']; target = config.get('target'); outcome='ALLOWED'; error=None
        try:
            if operation in ('file_read_canary','filesystem','credential_boundary'):
                require(Path(target).read_bytes()==b'IIOS_SYNTHETIC_CANARY\n', 'CANARY')
            elif operation=='network':
                with socket.create_connection(('127.0.0.1',config['target_port']),timeout=2):pass
            elif operation=='subprocess':
                subprocess.run(['/usr/bin/true'], check=True, timeout=2, env={'PATH':'/usr/bin:/bin'})
            elif operation!='identity':raise ValueError('PROBE_OPERATION')
        except PermissionError as exc:outcome='DENIED';error=exc.errno
        send(config,'DATA',outcome=outcome,errno=error)
    else:
        from truth_spine_contract import seal, verified
        from truth_spine_observation_roles import seed
        from provider_gateway_contract import content_hash
        if config['role']=='scheduler':
            previous=None;records=[]
            for slot in range(3):
                row=seed(slot,previous);records.append(row);previous=content_hash(row)
            value=seal(dict(schema='iios-native-v2-seeded-ledger',records=records,
                            nonce=config['nonce'],authority=AUTHORITY,executed_requests=0))
            publish(work/'seeded-ledger.json',value);send(config,'DATA',parent=value['content_hash'])
        elif config['role']=='publisher':
            ledger=verified(decode((work/'seeded-ledger.json').read_bytes()));previous=None
            require(ledger['nonce']==config['session'] and ledger['executed_requests']==0, 'LEDGER_SCOPE')
            require(len(ledger['records'])==3,'SEED_COUNT')
            for slot,row in enumerate(ledger['records']):
                require(row==seed(slot,previous),'SEED_CHAIN');previous=content_hash(row)
            value=seal(dict(schema='iios-native-v2-truth-projection',parent=ledger['content_hash'],
                            authority=AUTHORITY,seeded_records=3,executed_requests=0,session=config['session']))
            publish(work/'projection.json',value);send(config,'DATA',parent=value['content_hash'])
        elif config['role']=='backend':
            import ssl
            from http.server import BaseHTTPRequestHandler, HTTPServer
            value=verified(decode((work/'projection.json').read_bytes()))
            require(value['session']==config['session'] and value['authority']==AUTHORITY,'PROJECTION_SCOPE')
            body=json.dumps(value,sort_keys=True).encode()
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def respond(self,head=False):
                    if self.path!='/health':self.send_error(404);return
                    self.send_response(200);self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(body)));self.end_headers()
                    if not head:self.wfile.write(body)
                def do_GET(self):self.respond()
                def do_HEAD(self):self.respond(True)
            server=HTTPServer(('127.0.0.1',config['port']),Handler)
            ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(config['certificate'],config['key'])
            server.socket=ctx.wrap_socket(server.socket,server_side=True)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            send(config,'DATA',port=server.server_port,parent=value['content_hash'])
        else:raise ValueError('ROLE')
    require(sys.stdin.readline().strip()=='STOP '+config['nonce'],'STOP')
    if config['role']=='backend':server.shutdown();server.server_close();thread.join(3);require(not thread.is_alive(),'THREAD_CLEANUP')
    origins={name:dict(path=str(Path(module.__file__).resolve()),sha256=file_hash(Path(module.__file__).resolve())) for name,module in list(sys.modules.items()) if getattr(module,'__file__',None) and Path(module.__file__).is_file()}
    send(config,'STOPPED',origins=origins)


if __name__=='__main__':
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.alarm(180)
    try:main()
    except BaseException as error:
        print(json.dumps({'event':'ERROR','category':type(error).__name__}),flush=True)
        raise SystemExit(1)
