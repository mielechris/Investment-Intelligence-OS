"""Bounded pilot planning only; never provider, lifecycle or execution authority.

The observation window is independently pinned, not inferred from the clock or
from the full-day request count. Calendar semantics require external review.
"""
from datetime import timedelta

from alpha_session_contract import validate_session, instant, require
from provider_gateway_contract import content_hash, pin, safe_document, PILOT, locked_authority
from provider_gateway_live_contract import request_parameters
from truth_spine_session import parse_session, Session

OBSERVATION_SCHEMA = 'iios-alpha-short-observation-window-v1'
PLAN_SCHEMA = 'iios-alpha-short-observation-plan-v1'
PACKAGE_SCHEMA = 'iios-alpha-short-observation-package-v1'
SCOPE = 'OFFLINE_INTEGRATION_ONLY'
MAX_REQUESTS = 3


def short_plan(contract, calendar, universe, spine_session, observation, *, expected, now, source_commit):
    require(type(expected) is dict and set(expected) == {
        'session', 'calendar', 'universe', 'truth_spine_session', 'observation'}, 'SHORT_PINS')
    validate_session(contract, calendar, universe,
                     expected={k: expected[k] for k in ('session', 'calendar', 'universe')}, now=now)
    require(source_commit == contract['source_commit'], 'SHORT_SOURCE')
    safe_document(spine_session); pin(spine_session, expected['truth_spine_session'])
    session = parse_session(spine_session)
    require(type(session) is Session and session.status in ('NORMAL', 'SHORTENED'), 'SHORT_EXCHANGE_SESSION')
    require(session.day == contract['session'] and session.open_at == instant(calendar['open']) and
            session.close_at == instant(calendar['close']), 'SHORT_CALENDAR_BINDING')
    safe_document(observation); pin(observation, expected['observation'])
    require(type(observation) is dict and set(observation) == {
        'schema', 'session', 'source_commit', 'start', 'symbols', 'maximum_requests', 'authority'}, 'SHORT_WINDOW_SCHEMA')
    require(observation['schema'] == OBSERVATION_SCHEMA and
            observation['session'] == session.day and observation['source_commit'] == source_commit, 'SHORT_WINDOW_BINDING')
    require(type(observation['maximum_requests']) is int and observation['maximum_requests'] == MAX_REQUESTS and
            observation['symbols'] == list(PILOT), 'SHORT_PILOT_BINDING')
    require(type(observation['authority']) is dict and set(observation['authority']) == set(locked_authority()) and
            all(v is False for v in observation['authority'].values()), 'SHORT_AUTHORITY')
    start = instant(observation['start'])
    require(start.microsecond == 0 and now < start and
            session.open_at <= start and start + timedelta(seconds=300) <= session.close_at, 'SHORT_WINDOW')
    return _plan(contract, expected, start)


def _plan(contract, expected, start):
    shutdown = start + timedelta(seconds=300)
    require(instant(contract['valid_from']) <= start - timedelta(seconds=60) and
            shutdown <= instant(contract['expires_at']), 'SHORT_VALIDITY')
    rows = []
    for slot in range(MAX_REQUESTS):
        at = start + timedelta(seconds=60 * slot)
        rows.append({'slot': slot, 'id': 'SHORT-PILOT' if slot == 0 else f'SHORT-OBSERVATION-{slot}',
                     'phase': 'PREFLIGHT' if slot == 0 else 'OBSERVATION',
                     'symbols': list(PILOT), 'symbol_hash': content_hash(list(PILOT)),
                     'valid_from': at.isoformat(), 'dispatch_before': (at + timedelta(seconds=5)).isoformat(),
                     'expires_at': (at + timedelta(seconds=25)).isoformat()})
    return {'schema': PLAN_SCHEMA, 'scope': SCOPE, 'session': contract['session'],
            'source_commit': contract['source_commit'], 'parents': dict(expected), 'rows': rows,
            'maximum_requests': MAX_REQUESTS, 'preflight_requests': 1, 'collection_requests': 2,
            'maximum_starts_per_rolling_minute': 3, 'timeout_seconds': 20,
            'maximum_age_seconds': 60,
            'maximum_response_bytes': 1_000_000, 'retry_count': 0, 'redirect_count': 0,
            'pagination_count': 0, 'fallback_count': 0, 'backfill_count': 0, 'enrichment_requests': 0,
            'startup_not_before': (start - timedelta(seconds=60)).isoformat(),
            'startup_deadline': start.isoformat(),
            'reconciliation_deadline': (start + timedelta(seconds=180)).isoformat(),
            'cleanup_reserve_seconds': 120, 'finalization_deadline': shutdown.isoformat(),
            'coverage': 'TEN_SYMBOL_PILOT_ONLY_NOT_FULL_UNIVERSE_OR_FULL_DAY',
            'timing_proof_required': 'ACTUAL_UTC_AND_MONOTONIC_NO_ACCELERATION',
            'route': {'provider': 'ALPHA_VANTAGE', 'endpoint': 'REALTIME_BULK_QUOTES', 'feed': 'real_time',
                      'method': 'GET', 'scheme': 'https', 'host': 'www.alphavantage.co', 'path': '/query',
                      'parameters': request_parameters('ALPHA_VANTAGE', list(PILOT), 'real_time',
                                                       function='REALTIME_BULK_QUOTES')},
            'evidence_policy': 'EPHEMERAL_PROVIDER_DATA_SANITIZED_RECEIPTS_ONLY',
            'stop_on': ['MISSING_ADMISSION', 'MISSED_WINDOW', 'CLOCK_REGRESSION', 'DEADLINE',
                        'AMBIGUOUS_REQUEST', 'INCOMPLETE_OR_STALE_COVERAGE', 'IDENTITY_MISMATCH',
                        'EVIDENCE_FAILURE', 'ALLOWANCE_EXHAUSTED', 'AUTHORITY_EXPIRED'],
            'lifecycle_requirements': ['EXISTING_TRUTH_SPINE', 'VERIFIED_OWNERSHIP_BEFORE_ACTION',
                                       'STARTUP_ACK', 'TLS_BEFORE_DISPATCH', 'RESERVE_BEFORE_DISPATCH',
                                       'PREFLIGHT_BEFORE_OBSERVATIONS', 'EXCLUSIVE_HASH_BOUND_PUBLICATION',
                                       'RECONCILE_EVERY_RESERVATION', 'COOPERATIVE_SHUTDOWN',
                                       'NO_SIGNAL_WITHOUT_REVERIFIED_OWNERSHIP', 'VERIFIED_EXIT_AND_LISTENER_CLEAR'],
            'authority': locked_authority(), 'execution_authorized': False, 'production_qualified': False}


def verify_short_plan(candidate, candidate_hash, *args, **kwargs):
    safe_document(candidate); pin(candidate, candidate_hash)
    rebuilt = short_plan(*args, **kwargs)
    require(content_hash(candidate) == content_hash(rebuilt), 'SHORT_PLAN_SUBSTITUTION')
    return rebuilt
