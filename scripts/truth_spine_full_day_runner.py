"""Future owner-authorized full-day runner. NOT executed by source acceptance.

No compressed clock or environment clock override is accepted. Package creation
and owner approval are separate steps. The exact topology pin is an explicit
owner input, never derived from an edited JSON file as an authorization shortcut.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time

from truth_spine_integration_runner import OwnedChildren, port_is_clear


def run(root, topology_pin, *, owner_session):
    # Package-local imports only. Never fall back to the authoritative checkout.
    if root != root.resolve() or root.parent != Path('/private/tmp') or not root.name.startswith('iios-truth-spine-full-day-'):
        raise ValueError('NEW_OWNER_AUTHORIZED_ISOLATED_ROOT_REQUIRED')
    if Path(__file__).resolve().parent != root/'release/backend' or Path(sys.executable) != root/'runtime/bin/python':
        raise ValueError('INSTALLED_PACKAGE_RUNNER_REQUIRED')
    raw = (root/'topology.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != topology_pin:
        raise ValueError('OWNER_TOPOLOGY_PIN_MISMATCH')
    backend = root/'release/backend'
    sys.path.insert(0, str(backend))
    from truth_spine_full_day_service import load_config
    from truth_spine_generations import GenerationStore, owner_path, immutable_file
    from truth_spine_integration import atomic
    from truth_spine_integration_service import Lease
    from truth_spine_contract import seal, canonical
    from truth_spine_session_package import RuntimeProbeReader, capacity_budget
    from truth_spine_session_supervisor import SessionSupervisor
    owner_path(root, root, directory=True)
    c, session, manifest, authority, registry = load_config(root/'topology.json')
    if owner_session != session.identity or not port_is_clear(c['port']):
        raise ValueError('SESSION_OR_PORT_PREFLIGHT_FAILED')
    if (root/'shutdown-receipt.json').exists():
        raise ValueError('COMPLETED_ROOT_NOT_REUSABLE')
    if shutil.disk_usage(root).free < capacity_budget(session, registry)['required_free_bytes']:
        raise ValueError('SESSION_DISK_RESERVATION_INSUFFICIENT')
    # A previous parent's surviving child is never adopted or signaled.
    barriers = []
    try:
        for role in ('runner', 'scheduler', 'publisher', 'backend'):
            barriers.append(Lease(root, role))
    except BaseException:
        for lease in reversed(barriers): lease.close()
        raise
    runner_lease = barriers[0]
    for lease in reversed(barriers[1:]): lease.close()
    children = OwnedChildren(root, port_clear=lambda: port_is_clear(c['port']),
                             service_module='truth_spine_full_day_service')
    supervisor = None
    report = {}
    try:
        runtime = json.loads((root/'runtime/runtime-manifest.json').read_bytes())
        python = root/'runtime/bin/python'
        hashes = {str(python): runtime['interpreter_sha256']}
        if runtime.get('process_executable'):
            hashes[runtime['process_executable']] = runtime['process_executable_hash']
        for name, expected in hashes.items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
                raise ValueError('INTERPRETER_IDENTITY_INVALID')
        store = GenerationStore(root, session.identity, registry, c['registry_hash'])
        def start(role):
            load_config(root/'topology.json')
            if hashlib.sha256((root/'topology.json').read_bytes()).hexdigest() != topology_pin:
                raise ValueError('TOPOLOGY_CHANGED')
            args = [str(python), '-B', '-m', 'truth_spine_full_day_service', '--config', str(root/'topology.json'), '--role', role]
            if role == 'backend': args += ['--port', str(c['port'])]
            launch = children.prepare_launch(role, args, executable_hashes=hashes,
                final_executable=runtime.get('process_executable', str(python)), port=c['port'] if role == 'backend' else None)
            owner_path(root/'logs', root, directory=True)
            log_path = root/'logs'/(role+'.log')
            if log_path.exists(): owner_path(log_path, root)
            fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            handle = os.fdopen(fd, 'ab'); children.logs.append(handle)
            process = subprocess.Popen(launch.argv, cwd=backend,
                env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(backend)},
                stdout=handle, stderr=handle)
            children.register(role, process, launch.argv, backend, c['port'] if role == 'backend' else None,
                              executable_hashes=hashes, launch=launch)
        reader = RuntimeProbeReader(root=root, manifest=manifest, manifest_pin=c['manifest_hash'],
                                    children=children, session=session, store=store)
        def probes(now, generation, watermark):
            try:
                evidence = reader.collect(now, generation, watermark)
            except (OSError, ValueError, KeyError, TypeError):
                evidence = {}
            atomic(root/'runtime-probes.json', seal({'probes': evidence, 'at': now.isoformat()}))
            return evidence
        supervisor = SessionSupervisor(session=session, store=store, children=children, authority=authority,
            approved_authority_hash=c['authority_hash'], release=manifest['release'], owners=c['owners'],
            start_child=start, probe_runtime=probes)
        interrupted = False
        def stop(*_):
            nonlocal interrupted
            interrupted = True
        signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
        until = time.monotonic() + max(0, (session.shutdown_end-datetime.now(timezone.utc)).total_seconds())
        while not supervisor.closed:
            if any(p.stat().st_size > 1024*1024 for p in (root/'logs').glob('*.log')):
                supervisor.lifecycle.fail('LOG_GROWTH_LIMIT')
                supervisor.finish(datetime.now(timezone.utc))
                break
            if interrupted or time.monotonic() >= until:
                supervisor.lifecycle.fail('RUNNER_STOP_OR_MONOTONIC_DEADLINE')
                supervisor.finish(datetime.now(timezone.utc))
                break
            supervisor.cycle()
            if not supervisor.closed: time.sleep(5)
        return 0 if supervisor.lifecycle.state.get('session_result') == 'COMPLETE' else 1
    finally:
        try:
            if supervisor is not None and not supervisor.closed:
                supervisor.finish(datetime.now(timezone.utc))
            else:
                children.cleanup(report)
            immutable_file(root/'shutdown-receipt.json', canonical(seal({
                'schema': 'iios-full-day-shadow-shutdown-v1', 'session': session.identity,
                'authority_hash': c['authority_hash'], 'release_manifest_hash': c['manifest_hash'],
                'cleanup': children.finished, 'at': datetime.now(timezone.utc).isoformat(),
                'lifecycle_hash': supervisor.lifecycle.state['content_hash'] if supervisor else None})))
        finally:
            runner_lease.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--owner-topology-sha256', required=True)
    parser.add_argument('--owner-session-identity', required=True)
    a = parser.parse_args()
    return run(a.root, a.owner_topology_sha256, owner_session=a.owner_session_identity)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({'status': 'FAILED_CLOSED', 'category': type(exc).__name__}))
        sys.exit(4)
