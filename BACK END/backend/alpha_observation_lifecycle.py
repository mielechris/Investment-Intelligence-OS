"""Offline production-observation topology design; not an execution capability.

Existing Truth Spine roles and probes are references, never a relabeled shadow
service. Evidence pins bind identity only; OS/provider semantics require later
independent verifiers. No file, process, credential or ledger I/O occurs here.
"""
from alpha_session_contract import instant, require
from alpha_session_package import verify_bound_package, sha
from alpha_short_observation import PACKAGE_SCHEMA
from provider_gateway_contract import content_hash, pin, safe_document, locked_authority
from truth_spine_session_supervisor import ROLES, REQUIRED_PROBES

SCHEMA = 'iios-alpha-observation-topology-design-v1'
SCOPE = 'OFFLINE_INTEGRATION_ONLY'
STAGES = ('OWNERSHIP', 'ACK', 'TLS', 'PREFLIGHT', 'OBSERVATION_1', 'OBSERVATION_2',
          'RECONCILIATION', 'SHUTDOWN', 'PUBLICATION')
PROOFS = {
    'OWNERSHIP': ('scheduler', 'publisher', 'backend'),
    'ACK': ('startup_receipt', 'listener_owner', 'parent_ack'),
    'TLS': ('peer_identity', 'trust_bundle'),
    'PREFLIGHT': ('reservation', 'response', 'completion', 'coverage', 'freshness'),
    'OBSERVATION_1': ('reservation', 'response', 'completion', 'coverage', 'freshness'),
    'OBSERVATION_2': ('reservation', 'response', 'completion', 'coverage', 'freshness'),
    'RECONCILIATION': ('journal', 'accounting'),
    'SHUTDOWN': ('scheduler', 'publisher', 'backend', 'listener_owner', 'stable_port_clear'),
    'PUBLICATION': ('projection', 'health_ready', 'export'),
}


def observation_topology(package, package_hash, plan, account, runtime, allowance, *,
                         bindings, bindings_hash, **package_inputs):
    verified = verify_bound_package(package, package_hash, plan, account, runtime, allowance, **package_inputs)
    require(verified['schema'] == PACKAGE_SCHEMA, 'OBSERVATION_SHORT_ONLY')
    safe_document(bindings); pin(bindings, bindings_hash)
    require(type(bindings) is dict and set(bindings) == {'schema', 'source_commit', 'session',
            'plan_parent', 'package_parent', 'release_parent', 'runtime_parent', 'generation', 'owners'},
            'OBSERVATION_BINDING_SCHEMA')
    require(bindings['schema'] == 'iios-alpha-observation-bindings-v1' and
            bindings['source_commit'] == verified['source_commit'] and bindings['session'] == verified['session'] and
            bindings['plan_parent'] == verified['parents']['plan'] and bindings['package_parent'] == package_hash and
            bindings['runtime_parent'] == runtime['runtime_manifest_sha256'], 'OBSERVATION_BINDING')
    require(all(sha(bindings[k]) for k in ('release_parent', 'generation', 'runtime_parent')) and
            type(bindings['owners']) is dict and set(bindings['owners']) == set(ROLES) and
            all(sha(v) for v in bindings['owners'].values()), 'OBSERVATION_OWNER_PINS')
    return {'schema': SCHEMA, 'scope': SCOPE, 'source_commit': verified['source_commit'],
            'session': verified['session'], 'package_parent': package_hash, 'bindings_parent': bindings_hash,
            'plan_parent': verified['parents']['plan'], 'truth_spine_session_parent': plan['parents']['truth_spine_session'],
            'generation': bindings['generation'], 'owners': dict(bindings['owners']),
            'roles': list(ROLES), 'required_probes': sorted(REQUIRED_PROBES), 'stages': list(STAGES),
            'channel': 'PROPOSED_SANITIZED_OBSERVATION_RECEIPTS_NO_LEDGER',
            'supervision': 'EXISTING_TRUTH_SPINE_ONLY', 'ownership_samples_per_role': 3,
            'reverify_before_signal': True, 'ack_after_ownership_receipt_and_listener': True,
            'tls_before_dispatch': True, 'restart_count': 0, 'retry_count': 0, 'maximum_requests': 3,
            'dispatch_checks': ['BEFORE_RESERVATION', 'BEFORE_HTTP_SEND'],
            'startup_not_before': plan['startup_not_before'], 'startup_deadline': plan['startup_deadline'],
            'reconciliation_deadline': plan['reconciliation_deadline'],
            'finalization_deadline': plan['finalization_deadline'], 'rows': plan['rows'],
            'authority': locked_authority(), 'production_qualified': False, 'execution_authorized': False,
            'pending': ['ACTUAL_PRODUCTION_TOPOLOGY_ADAPTER', 'OS_CONFINEMENT', 'NATIVE_OWNERSHIP_TLS_CLEANUP',
                        'CURRENT_ACCOUNT_EVIDENCE', 'REAL_PROVIDER_PREFLIGHT', 'EXECUTION_AUTHORITY']}


def verify_topology(candidate, topology_hash, **inputs):
    safe_document(candidate); pin(candidate, topology_hash)
    rebuilt = observation_topology(**inputs)
    require(content_hash(candidate) == content_hash(rebuilt), 'OBSERVATION_TOPOLOGY_SUBSTITUTION')
    return rebuilt


def reduce_design(topology, evidence, stage_pins):
    """Called only after reconstruction. Complete fake proofs remain offline only."""
    require(type(evidence) is dict and type(stage_pins) is dict and
            set(evidence) <= set(STAGES) and set(stage_pins) == set(evidence), 'OBSERVATION_STAGE_SET')
    count = len(evidence)
    previous = None; last_time = instant(topology['startup_not_before']); last_mono = -1
    failed = False; checks = {}; used = set()
    last_counts = dict.fromkeys(('reservations', 'responses', 'completions'), 0)
    for stage in STAGES:
        if stage not in evidence:
            checks[stage] = 'MISSING'
            continue
        require(not any(checks.get(s) == 'MISSING' for s in STAGES[:STAGES.index(stage)]) or
                (failed and stage in ('SHUTDOWN', 'PUBLICATION')), 'OBSERVATION_STAGE_GAP')
        item = evidence[stage]; safe_document(item); pin(item, stage_pins[stage])
        require(type(item) is dict and set(item) == {'schema', 'scope', 'classification', 'stage', 'source_commit',
            'session', 'topology_parent', 'previous', 'generation', 'owners', 'observed_at', 'monotonic_ns',
            'dispatch_at', 'result', 'proofs', 'counts', 'authority'}, 'OBSERVATION_STAGE_SCHEMA')
        require(item['schema'] == 'iios-alpha-observation-design-stage-v1' and item['scope'] == SCOPE and
                item['classification'] == 'DESIGN_TEST_ONLY' and item['stage'] == stage and
                all(item[k] == topology[k] for k in ('source_commit', 'session', 'generation', 'owners')) and
                item['topology_parent'] == content_hash(topology) and item['previous'] == previous,
                'OBSERVATION_STAGE_BINDING')
        require(type(item['authority']) is dict and set(item['authority']) == set(locked_authority()) and
                all(v is False for v in item['authority'].values()), 'OBSERVATION_AUTHORITY')
        require(item['result'] in ('PASS', 'FAILED'), 'OBSERVATION_RESULT')
        require(type(item['proofs']) is dict and set(item['proofs']) <= set(PROOFS[stage]) and
                (item['result'] == 'FAILED' or set(item['proofs']) == set(PROOFS[stage])) and
                all(sha(p) for p in item['proofs'].values()), 'OBSERVATION_PROOFS')
        require(item['result'] in ('PASS', 'FAILED') and
                (not failed or stage in ('SHUTDOWN', 'PUBLICATION')), 'OBSERVATION_AFTER_FAILURE')
        at = instant(item['observed_at'])
        require(last_time <= at <= instant(topology['finalization_deadline']) and
                type(item['monotonic_ns']) is int and last_mono < item['monotonic_ns'] < 2**63,
                'OBSERVATION_CLOCK')
        expected_count = 0 if stage in STAGES[:3] else min(STAGES.index(stage)-2, 3)
        require(type(item['counts']) is dict and set(item['counts']) == {'reservations', 'responses', 'completions'} and
                all(type(v) is int and 0 <= v <= 3 for v in item['counts'].values()), 'OBSERVATION_COUNTS')
        require(0 <= item['counts']['completions'] <= item['counts']['responses'] <= item['counts']['reservations'] <= 3 and
                all(item['counts'][k] >= v for k,v in last_counts.items()), 'OBSERVATION_COUNT_ROLLBACK')
        if item['result'] == 'PASS':
            require(item['counts'] == last_counts if failed else set(item['counts'].values()) == {expected_count},
                    'OBSERVATION_ACCOUNTING')
        if stage in STAGES[:3]:
            require(at < instant(topology['startup_deadline']) and item['dispatch_at'] is None, 'OBSERVATION_STARTUP_DEADLINE')
        elif stage in STAGES[3:6]:
            row = topology['rows'][STAGES.index(stage)-3]; dispatch = instant(item['dispatch_at'])
            require(last_time <= dispatch <= at and instant(row['valid_from']) <= dispatch < instant(row['dispatch_before']) and
                    at < instant(row['expires_at']), 'OBSERVATION_DISPATCH_WINDOW')
            for k in ('reservation', 'response', 'completion'):
                if k in item['proofs']:
                    require(item['proofs'][k] not in used, 'OBSERVATION_REQUEST_REPLAY'); used.add(item['proofs'][k])
        else:
            require(item['dispatch_at'] is None, 'OBSERVATION_NO_DISPATCH')
            if stage == 'RECONCILIATION': require(at <= instant(topology['reconciliation_deadline']), 'OBSERVATION_RECONCILIATION_DEADLINE')
        failed |= item['result'] != 'PASS'
        checks[stage] = item['result']; previous = stage_pins[stage]; last_time = at; last_mono = item['monotonic_ns']
        last_counts = dict(item['counts'])
    return {'schema': 'iios-alpha-observation-design-join-v1', 'scope': SCOPE,
            'topology_parent': content_hash(topology), 'stage_parents': dict(stage_pins), 'checks': checks,
            'status': 'OFFLINE_COMPLETE' if count == len(STAGES) and not failed else 'BLOCKED',
            'authority': locked_authority(), 'production_qualified': False, 'execution_authorized': False,
            'native_semantics_verified': False, 'provider_requests': 0}
