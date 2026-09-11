"""Monday-only readiness contracts. No scheduler, credential or provider I/O."""
from datetime import timedelta

from alpha_market_baseline import plan, require
from provider_gateway_contract import PILOT, content_hash, pin, utc

FLAGS = ('broker_connected', 'paper_order_permission', 'trade_execution_permission', 'live_execution')
STAGES = ('universe', 'preflight', 'opening', 'intraday', 'closing', 'yahoo_discovery',
          'candidates_cases', 'agents', 'committee', 'risk', 'paper_decision')


def readiness_plan(universe, universe_hash, calendar, calendar_hash, *, root):
    value = plan(universe, universe_hash, calendar, calendar_hash, root=root)
    opening = utc(calendar['open'])
    rows = [{'slot': 0, 'id': 'PREFLIGHT-0', 'phase': 'PREFLIGHT', 'batch': 0,
             'symbols': list(PILOT), 'symbol_hash': content_hash(list(PILOT)),
             'valid_from': (opening - timedelta(minutes=10)).isoformat(),
             'expires_at': (opening - timedelta(minutes=5)).isoformat(),
             'root': root + '/PREFLIGHT-0'}]
    for old in value['rows']:
        row = dict(old)
        phase = row['phase']
        anchor = opening + timedelta(seconds=30) if phase == 'OPENING' else opening + timedelta(hours=3) if phase == 'INTRADAY' else utc(calendar['close']) + timedelta(seconds=30)
        duration = 120 if phase == 'INTRADAY' else 100
        row.update(slot=len(rows), valid_from=anchor.isoformat(), expires_at=(anchor + timedelta(seconds=duration)).isoformat())
        rows.append(row)
    value.update(schema='iios-alpha-session-plan-v2', rows=rows, maximum_requests=19,
                 collection_requests=18, preflight_requests=1, maximum_starts_per_rolling_minute=3,
                 requires_preflight=True, response_must_finish_in_interval=True)
    return value


def final_session_receipt(evidence, expected, *, session='2026-09-14', scope='OFFLINE_TEST'):
    """Join independently accepted stage receipts, never generate missing evidence.

    External stage semantics must be verified by their existing governance owners
    before their hashes enter `expected`. A hash is not a substitute for that review.
    OFFLINE_TEST can never establish live acceptance, including synthetic all-PASS.
    """
    require(session == '2026-09-14' and scope in ('OFFLINE_TEST', 'LIVE_EVIDENCE'), 'SESSION_SCOPE')
    require(set(evidence) <= set(STAGES) and set(expected) == set(evidence), 'EVIDENCE_SET')
    checks, parents, previous = {}, {}, None
    for stage in STAGES:
        if stage not in evidence:
            checks[stage] = 'MISSING'
            previous = None
            continue
        receipt = evidence[stage]
        pin(receipt, expected[stage])
        parents[stage] = expected[stage]
        require(receipt.get('stage') == stage and receipt.get('session') == session and
                receipt.get('scope') == scope, 'STAGE_IDENTITY')
        require(receipt.get('previous') == previous, 'STAGE_PARENT')
        require(receipt.get('authority') == dict.fromkeys(FLAGS, False), 'STAGE_AUTHORITY')
        checks[stage] = 'PASS' if receipt.get('result') == 'PASS' else 'FAILED_OR_UNVERIFIED'
        previous = expected[stage]
    result = 'GREEN' if scope == 'LIVE_EVIDENCE' and all(checks[s] == 'PASS' for s in STAGES) else 'RED' if any(v == 'FAILED_OR_UNVERIFIED' for v in checks.values()) else 'YELLOW'
    return {'schema': 'iios-monday-session-join-v1', 'session': session, 'scope': scope,
            'status': result, 'parents': parents, 'checks': checks, **dict.fromkeys(FLAGS, False),
            'independent_stage_acceptance_required': True}
