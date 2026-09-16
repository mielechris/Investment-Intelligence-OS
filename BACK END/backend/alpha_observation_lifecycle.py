"""Separate observation design and independently qualified execution admission.

Existing Truth Spine roles and probes are references, never a relabeled shadow
service. Evidence pins bind identity only; OS/provider semantics require later
independent verifiers. Design functions have no effects; execution admission
reads only independently approved immutable release and evidence files.
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


# These admission documents are distinct from all design/component receipts.
EXECUTION_SCHEMA = 'iios-truth-observation-execution-v1'
EXECUTION_SCOPE = 'BOUNDED_REAL_PROVIDER_OBSERVATION'
QUALIFICATION_KINDS = ('runtime', 'host', 'confinement', 'lifecycle', 'account')
QUALIFICATION_CHECKS = {
    'runtime': ('final_destination', 'complete_closure', 'module_origins', 'loaded_libraries', 'ownership'),
    'host': ('selected_host', 'os_build', 'architecture', 'tool_identities'),
    'confinement': ('default_deny', 'attributed_denials', 'controlled_comparisons', 'filesystem',
                    'network', 'subprocess', 'credential_boundary'),
    'lifecycle': ('startup', 'three_observations', 'ack', 'listener_owner', 'tls',
                  'cooperative_shutdown', 'verified_exit', 'stable_port_clear'),
    'account': ('endpoint', 'symbols', 'feed', 'rate', 'cost', 'internal_use', 'billing',
                'selector_binding', 'retention'),
}


class ObservationExecution:
    """Immutable admission identity; no caller boolean or callback grants access."""
    __slots__ = ('_document', '_expected', '_roots', '_pins')

    def __init__(self, *args, **kwargs):
        raise TypeError('OBSERVATION_ADMISSION_FACTORY_REQUIRED')

    def __setattr__(self, name, value):
        raise AttributeError('OBSERVATION_CAPABILITY_IMMUTABLE')

    def document(self):
        import json
        return json.loads(self._document)

    @property
    def identity(self):
        return self._expected

    def recheck(self, now):
        import json
        return admit_observation_execution(self.document(), self._expected,
            approved_roots=json.loads(self._roots), approved_qualification_pins=json.loads(self._pins), now=now)


def admit_observation_execution(document, expected, *, approved_roots,
                                approved_qualification_pins, now):
    """Admission to the fixed three-request path, not global production readiness.

    Invocation roots and qualification pins are independently owner-reviewed
    inputs. Documents cannot nominate their own trust roots. Actual qualification
    results must exist; this routine never converts a component PASS or generic
    permission error into a confinement/production result.
    """
    from copy import deepcopy
    from provider_gateway_contract import canonical
    from alpha_session_evidence import verify_candidate_evidence, verify_files, json_document
    from alpha_session_package import verify_observation_release
    from alpha_observation_launch import lexical
    safe_document(document); pin(document, expected)
    fields = {'schema', 'scope', 'source_commit', 'roots', 'preflight', 'release', 'release_parent',
        'qualifications', 'qualification_files', 'grant', 'grant_parent', 'launch', 'authority'}
    require(type(document) is dict and set(document) == fields, 'OBSERVATION_EXECUTION_SCHEMA')
    d = document
    require(d['schema'] == EXECUTION_SCHEMA and d['scope'] == EXECUTION_SCOPE,
            'OBSERVATION_EXECUTION_SCOPE')
    require(type(approved_roots) is dict and set(approved_roots) == {
        'runtime', 'claims', 'release', 'qualification', 'control', 'output'} and
        d['roots'] == approved_roots, 'OBSERVATION_APPROVED_ROOTS')
    paths = [lexical(p) for p in approved_roots.values()]
    require(all(not a.is_relative_to(b) and not b.is_relative_to(a)
        for i, a in enumerate(paths) for b in paths[i+1:]), 'OBSERVATION_ROOT_ALIAS')
    require(d['authority'] == locked_authority() and
        all(v is False for v in d['authority'].values()), 'OBSERVATION_AUTHORITY')
    b = d['preflight']
    from alpha_session_preflight import FIELDS, INPUT_FIELDS
    require(type(b) is dict and set(b) == FIELDS and
        b['schema'] == 'iios-alpha-short-preflight-input-v1' and
        set(b['package_inputs']) == INPUT_FIELDS | {'observation'}, 'OBSERVATION_PREFLIGHT_SCHEMA')
    inputs = b['package_inputs']
    require(inputs['source_commit'] == d['source_commit'], 'OBSERVATION_SOURCE')
    evidence = verify_candidate_evidence(b['candidate'], b['candidate_hash'], b['plan'], b['account'],
        b['runtime'], b['allowance'], runtime_manifest=b['runtime_manifest'],
        claims_manifest=b['claims_manifest'], claims_manifest_hash=b['claims_manifest_hash'],
        approved_runtime_root=approved_roots['runtime'], approved_claims_root=approved_roots['claims'],
        now=instant(b['plan']['startup_not_before']), **inputs)
    verify_observation_release(d['release'], d['release_parent'], source_commit=d['source_commit'],
                               approved_root=approved_roots['release'])
    require(type(approved_qualification_pins) is dict and
        set(approved_qualification_pins) == set(QUALIFICATION_KINDS) and
        all(sha(v) for v in approved_qualification_pins.values()) and
        len(set(approved_qualification_pins.values())) == len(QUALIFICATION_KINDS),
        'OBSERVATION_INDEPENDENT_QUALIFICATION_PINS')
    require(type(d['qualifications']) is dict and set(d['qualifications']) == set(QUALIFICATION_KINDS),
            'OBSERVATION_QUALIFICATION_SET')
    names = [kind + '.json' for kind in QUALIFICATION_KINDS]
    bodies = verify_files(approved_roots['qualification'], d['qualification_files'],
        approved_root=approved_roots['qualification'], retain=names)
    launch = d['launch']
    require(type(launch) is dict and set(launch) == {'host', 'port', 'peer_hash', 'sandbox_hash',
        'control_files', 'host_identity', 'start_ns', 'startup_ns', 'stop_ns', 'final_ns'}, 'OBSERVATION_LAUNCH_SCHEMA')
    require(launch['host'] == '127.0.0.1' and type(launch['port']) is int and
        1024 < launch['port'] < 65536 and sha(launch['peer_hash']) and sha(launch['sandbox_hash']),
        'OBSERVATION_LAUNCH_ENDPOINT')
    require(all(type(launch[k]) is int and 0 < launch[k] < 2**63
        for k in ('start_ns','startup_ns','stop_ns','final_ns')), 'OBSERVATION_LAUNCH_CLOCK')
    require(launch['start_ns'] < launch['startup_ns'] < launch['stop_ns'] < launch['final_ns'] and
        launch['startup_ns']-launch['start_ns'] <= 60_000_000_000 and
        launch['final_ns']-launch['start_ns'] <= 360_000_000_000 and
        launch['final_ns']-launch['stop_ns'] >= 120_000_000_000, 'OBSERVATION_LAUNCH_BUDGET')
    start=instant(b['plan']['startup_not_before'])
    for ns_key,utc_key in (('startup_ns','startup_deadline'),('stop_ns','reconciliation_deadline'),
                          ('final_ns','finalization_deadline')):
        delta=instant(b['plan'][utc_key])-start
        expected_ns=(delta.days*86400+delta.seconds)*1_000_000_000+delta.microseconds*1000
        require(launch[ns_key]-launch['start_ns']==expected_ns,'OBSERVATION_PHASE_DEADLINE_BINDING')
    require(set(launch['host_identity']) == {'system','release','version','machine','uid'} and
        launch['host_identity']['system'] == 'Darwin' and launch['host_identity']['machine'] == 'arm64' and
        type(launch['host_identity']['uid']) is int, 'OBSERVATION_HOST_SCHEMA')
    require({r['path'] for r in launch['control_files']} == {'profile.sb','loopback.crt','loopback.pem'},
        'OBSERVATION_CONTROL_FILES')
    verify_files(approved_roots['control'], launch['control_files'], approved_root=approved_roots['control'])
    parents = {'launch': content_hash(launch), 'package': b['candidate_hash'], 'release': d['release_parent'],
        'runtime': b['runtime']['runtime_manifest_sha256'], 'claims': b['claims_manifest_hash'],
        'roots': content_hash(approved_roots), 'session': b['plan']['session']}
    host_parent = approved_qualification_pins['host']
    for kind in QUALIFICATION_KINDS:
        q = json_document(bodies[kind + '.json']); pin(q, approved_qualification_pins[kind])
        require(d['qualifications'][kind] == q and set(q) == {
            'schema', 'scope', 'kind', 'source_commit', 'parents', 'host_parent', 'valid_from',
            'expires_at', 'checks', 'evidence_parents', 'authority'}, 'OBSERVATION_QUALIFICATION_SCHEMA')
        require(q['schema'] == 'iios-reviewed-observation-qualification-v1' and
            q['scope'] == EXECUTION_SCOPE and q['kind'] == kind and
            q['source_commit'] == d['source_commit'] and q['parents'] == parents and
            q['host_parent'] == (None if kind == 'host' else host_parent), 'OBSERVATION_QUALIFICATION_BINDING')
        require(instant(q['valid_from']) <= now < instant(q['expires_at']) and
            instant(q['expires_at']) >= instant(b['plan']['finalization_deadline']),
            'OBSERVATION_QUALIFICATION_EXPIRED')
        require(type(q['checks']) is dict and set(q['checks']) == set(QUALIFICATION_CHECKS[kind]) and
            all(v == 'INDEPENDENTLY_QUALIFIED' for v in q['checks'].values()),
            'OBSERVATION_QUALIFICATION_UNPROVEN')
        require(type(q['evidence_parents']) is dict and set(q['evidence_parents']) == set(q['checks']) and
            all(sha(v) for v in q['evidence_parents'].values()) and
            q['authority'] == locked_authority() and all(v is False for v in q['authority'].values()),
            'OBSERVATION_QUALIFICATION_EVIDENCE')
    g = d['grant']; pin(g, d['grant_parent'])
    require(set(g) == {'schema', 'scope', 'source_commit', 'parents', 'qualification_parents',
        'valid_from', 'expires_at', 'maximum_requests', 'maximum_cost', 'cost_unit',
        'retry_count', 'authority'}, 'OBSERVATION_GRANT_SCHEMA')
    require(g['schema'] == 'iios-owner-observation-grant-v1' and g['scope'] == EXECUTION_SCOPE and
        g['source_commit'] == d['source_commit'] and g['parents'] == parents and
        g['qualification_parents'] == approved_qualification_pins and
        g['authority'] == locked_authority() and all(v is False for v in g['authority'].values()),
        'OBSERVATION_GRANT_BINDING')
    require(type(g['maximum_requests']) is int and g['maximum_requests'] == 3 and
        type(g['retry_count']) is int and g['retry_count'] == 0 and
        g['maximum_cost'] == b['allowance']['maximum_cost'] and g['cost_unit'] == b['allowance']['cost_unit'],
        'OBSERVATION_GRANT_BUDGET')
    require(instant(g['valid_from']) <= now < instant(g['expires_at']) and
        instant(g['valid_from']) <= instant(b['plan']['startup_not_before']) and
        instant(g['expires_at']) == instant(b['plan']['finalization_deadline']), 'OBSERVATION_GRANT_WINDOW')
    require(evidence['package_parent'] == b['candidate_hash'], 'OBSERVATION_PACKAGE_PARENT')
    value = object.__new__(ObservationExecution)
    object.__setattr__(value, '_document', canonical(deepcopy(d)))
    object.__setattr__(value, '_expected', expected)
    object.__setattr__(value, '_roots', canonical(approved_roots))
    object.__setattr__(value, '_pins', canonical(approved_qualification_pins))
    return value


def verify_observation_execution(value, expected, *, now):
    require(type(value) is ObservationExecution and value.identity == expected, 'OBSERVATION_CAPABILITY_REQUIRED')
    return value.recheck(now)
