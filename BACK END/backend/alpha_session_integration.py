"""Pure Radar/Truth Spine planning bridge. No execution, ledger or provider I/O."""
from copy import deepcopy
from datetime import timedelta

from alpha_session_contract import validate_session, instant, require
from alpha_session_readiness import STAGES, FLAGS
from provider_gateway_contract import content_hash, pin, PILOT, locked_authority, safe_document
from truth_spine_session import parse_session, Session

PLAN_SCHEMA = 'iios-alpha-session-candidate-v1'
SCOPE = 'OFFLINE_INTEGRATION_ONLY'


def session_plan(contract, calendar, universe, spine_session, *, expected, now, source_commit):
    """Reconcile independently pinned identities with the existing Truth Spine.

    The returned candidate is deliberately not an executable package schema.
    The caller must already have independently reviewed calendar evidence.
    """
    require(type(expected) is dict and set(expected) == {
        'session', 'calendar', 'universe', 'truth_spine_session'}, 'INTEGRATION_PINS')
    base = {key: expected[key] for key in ('session', 'calendar', 'universe')}
    validate_session(contract, calendar, universe, expected=base, now=now)
    require(source_commit == contract['source_commit'], 'INTEGRATION_SOURCE')
    safe_document(spine_session)
    pin(spine_session, expected['truth_spine_session'])
    session = parse_session(spine_session)
    require(type(session) is Session and session.status == 'NORMAL', 'NORMAL_SESSION_REQUIRED')
    require(session.day == contract['session'] and session.open_at == instant(calendar['open']) and
            session.close_at == instant(calendar['close']), 'TRUTH_SPINE_SESSION_MISMATCH')
    opening, closing = session.open_at, session.close_at
    require(closing-opening == timedelta(hours=6, minutes=30), 'NORMAL_SESSION_DURATION')
    require(instant(contract['valid_from']) <= opening-timedelta(minutes=10) and
            instant(contract['expires_at']) >= session.reconcile_end, 'COMPLETE_SESSION_WINDOW')
    batches = [universe[i:i+100] for i in range(0, 517, 100)]
    rows = [{'slot': 0, 'id': 'PREFLIGHT-0', 'phase': 'PREFLIGHT', 'batch': 0,
             'symbols': list(PILOT), 'symbol_hash': content_hash(list(PILOT)),
             'valid_from': (opening-timedelta(minutes=10)).isoformat(),
             'expires_at': (opening-timedelta(minutes=5)).isoformat()}]
    for scan in range(79):
        start = opening+timedelta(seconds=30, minutes=5*scan)
        end = start+timedelta(minutes=5)
        for batch, members in enumerate(batches):
            rows.append({'slot': len(rows), 'id': f'SCAN-{scan:02d}-{batch}', 'phase': 'SCAN',
                         'scan': scan, 'batch': batch, 'symbols': list(members),
                         'symbol_hash': content_hash(members), 'valid_from': start.isoformat(),
                         'expires_at': end.isoformat()})
    # The existing 79-scan policy includes a closing scan after the exchange close.
    # It must fit the separately bound reconciliation window, never a new allowance.
    require(instant(rows[-1]['expires_at']) <= session.reconcile_end, 'FINAL_SCAN_WINDOW')
    return {'schema': PLAN_SCHEMA, 'scope': SCOPE, 'session': session.day,
            'source_commit': source_commit, 'parents': dict(expected), 'rows': rows,
            'maximum_requests': 475, 'collection_requests': 474, 'preflight_requests': 1,
            'maximum_starts_per_rolling_minute': 3, 'timeout_seconds': 20,
            'maximum_response_bytes': 1_000_000, 'retry_count': 0,
            'finalization_deadline': session.reconcile_end.isoformat(),
            'authority': locked_authority(), 'execution_authorized': False,
            'production_qualified': False}


def verify_session_plan(candidate, candidate_hash, contract, calendar, universe, spine_session,
                        *, expected, now, source_commit, observation=None):
    from alpha_short_observation import PLAN_SCHEMA as SHORT_SCHEMA, verify_short_plan
    if type(candidate) is dict and candidate.get('schema') == SHORT_SCHEMA:
        return verify_short_plan(candidate, candidate_hash, contract, calendar, universe, spine_session,
                                 observation, expected=expected, now=now, source_commit=source_commit)
    require(observation is None, 'FULL_SESSION_OBSERVATION_FORBIDDEN')
    safe_document(candidate)
    pin(candidate, candidate_hash)
    rebuilt = session_plan(contract, calendar, universe, spine_session,
                           expected=expected, now=now, source_commit=source_commit)
    # Python equality treats False == 0 and 475 == 475.0. Compare canonical
    # identities so rehashed type substitutions cannot pass reconstruction.
    require(content_hash(candidate) == content_hash(rebuilt), 'SESSION_PLAN_SUBSTITUTION')
    return deepcopy(rebuilt)


def offline_stage_join(candidate, candidate_hash, evidence, stage_pins, *, contract, calendar,
                       universe, spine_session, expected, now, source_commit):
    """Prepare session-bound joins for existing owners; never accept live results.

    Receipts must explicitly name this offline scope and independently pinned
    candidate. Hash verification cannot replace semantic acceptance by each owner.
    """
    plan = verify_session_plan(candidate, candidate_hash, contract, calendar, universe, spine_session,
                               expected=expected, now=now, source_commit=source_commit)
    require(type(evidence) is dict and type(stage_pins) is dict and
            set(evidence) <= set(STAGES) and set(stage_pins) == set(evidence), 'STAGE_SET')
    checks, previous = {}, None
    for stage in STAGES:
        if stage not in evidence:
            checks[stage] = 'MISSING'
            previous = None
            continue
        value = evidence[stage]
        safe_document(value)
        pin(value, stage_pins[stage])
        require(type(value) is dict and set(value) == {
            'stage', 'session', 'scope', 'source_commit', 'plan_parent', 'previous',
            'result', 'authority'}, 'STAGE_SCHEMA')
        require(value['stage'] == stage and value['session'] == plan['session'] and
                value['scope'] == SCOPE and value['source_commit'] == source_commit and
                value['plan_parent'] == candidate_hash and value['previous'] == previous, 'STAGE_BINDING')
        require(type(value['authority']) is dict and set(value['authority']) == set(FLAGS) and
                all(v is False for v in value['authority'].values()), 'STAGE_AUTHORITY')
        require(value['result'] in ('PASS', 'FAILED', 'BLOCKED'), 'STAGE_RESULT')
        checks[stage] = value['result']
        previous = stage_pins[stage]
    return {'schema': 'iios-alpha-offline-stage-join-v1', 'scope': SCOPE,
            'session': plan['session'], 'source_commit': source_commit,
            'plan_parent': candidate_hash, 'stage_parents': dict(stage_pins), 'checks': checks,
            'status': 'BLOCKED' if any(v != 'PASS' for v in checks.values()) else 'OFFLINE_COMPLETE',
            'production_qualified': False, 'execution_authorized': False, 'authority': locked_authority()}
