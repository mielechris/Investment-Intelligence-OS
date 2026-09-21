#!/usr/bin/env python3
"""Selected-Mac prerequisite for unified-log sandbox-denial attribution.

This is a single disposable denied file read.  It is not qualification and
does not load providers, credentials, or any trading authority.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE/'BACK END/backend'))
from iios_qualification_v2.native import (collect_os_denial_attribution, profile,
                                           require_os_denial_attribution)
from iios_qualification_v2.runtime import ENV


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',required=True,type=Path)
    args=parser.parse_args()
    runtime=args.runtime.resolve();python=runtime/'bin/python'
    if not (python.is_file() and os.access(python,os.X_OK)):
        raise ValueError('PREREQUISITE_RUNTIME_UNAVAILABLE')
    with tempfile.TemporaryDirectory(prefix='iios-os-denial-attribution-') as raw:
        work=Path(raw);work.chmod(0o700)
        target=work/'synthetic-denied-canary';target.write_bytes(b'IIOS_SYNTHETIC_CANARY\n');target.chmod(0o600)
        policy=work/'probe.sb';policy.write_text(profile(SOURCE,runtime,work,python,38493,target));policy.chmod(0o400)
        code=('from pathlib import Path; import sys; '
              'p=Path(sys.argv[1]); '
              'exec("try:\\n p.read_bytes()\\nexcept PermissionError: raise SystemExit(0)\\nraise SystemExit(64)")')
        child=subprocess.Popen(['/usr/bin/sandbox-exec','-f',str(policy),str(python),'-I','-B','-S','-c',code,str(target)],
                               cwd=work,env=ENV,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,close_fds=True)
        if child.wait(timeout=15)!=0:
            raise ValueError('PREREQUISITE_SANDBOX_DENIAL_NOT_OBSERVED')
        deadline=time.monotonic()+10;file_telemetry=None
        while time.monotonic()<deadline:
            file_telemetry=collect_os_denial_attribution(child.pid,'file-read-data',target)
            if file_telemetry['tool_exit_timeout_category']=='EXIT_0' and file_telemetry['all_fields_attributable_count']>0:break
            time.sleep(0.5)
        if file_telemetry is None:raise ValueError('PREREQUISITE_TELEMETRY_UNAVAILABLE')
        require_os_denial_attribution(file_telemetry)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen();port=listener.getsockname()[1]
            if port==38493:raise ValueError('NETWORK_REPRESENTATION_PORT_COLLISION')
            network_policy=work/'network-probe.sb'
            # Match Native.launch: the sandbox retains its fixed controller
            # port while the synthetic probe attempts a distinct target port.
            network_policy.write_text(profile(SOURCE,runtime,work,python,38493,target));network_policy.chmod(0o400)
            network_code=('import socket,sys; '
                          'exec("try:\\n socket.create_connection((\'127.0.0.1\',int(sys.argv[1])),timeout=2)\\n'
                          'except PermissionError: raise SystemExit(0)\\nraise SystemExit(64)")')
            network_child=subprocess.Popen(['/usr/bin/sandbox-exec','-f',str(network_policy),str(python),'-I','-B','-S',
                                            '-c',network_code,str(port)],cwd=work,env=ENV,stdin=subprocess.DEVNULL,
                                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True)
            if network_child.wait(timeout=15)!=0:
                raise ValueError('NETWORK_REPRESENTATION_DENIAL_NOT_OBSERVED')
            expected='127.0.0.1:'+str(port);deadline=time.monotonic()+10;network_telemetry=None
            while time.monotonic()<deadline:
                network_telemetry=collect_os_denial_attribution(network_child.pid,'network-outbound',expected)
                if network_telemetry['target_representation_counts'].get('REMOTE_WILDCARD_HOST_EXACT_PORT',0)>0:break
                time.sleep(0.5)
        if network_telemetry is None:raise ValueError('NETWORK_REPRESENTATION_TELEMETRY_UNAVAILABLE')
        if (network_telemetry['tool_exit_timeout_category']!='EXIT_0' or
                network_telemetry['target_representation_counts'].get('REMOTE_WILDCARD_HOST_EXACT_PORT',0)<1):
            raise ValueError('NETWORK_REPRESENTATION_NOT_REPRODUCED')
        if network_telemetry['target_match_count']!=0 or network_telemetry['all_fields_attributable_count']!=0:
            raise ValueError('WILDCARD_TARGET_INCORRECTLY_ATTRIBUTED')
        print(json.dumps(dict(schema=1,prerequisite='SYNTHETIC_MACOS_SANDBOX_DENIAL',status='GREEN',
                              pid_bound=True,operation_bound=True,file_exact_target_bound=True,
                              telemetry=file_telemetry,network_representation_regression='GREEN',
                              network_telemetry=network_telemetry,exact_target_proven=False,
                              qualification_attribution='RED',qualification_launched=False,provider_requests=0,
                              credentials_accessed=False,trade_execution=False),sort_keys=True))


if __name__=='__main__':
    main()
