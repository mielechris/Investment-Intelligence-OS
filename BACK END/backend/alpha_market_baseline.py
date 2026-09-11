"""Governed Alpha bulk planning and ephemeral decoding; no I/O or activation."""
from collections import Counter
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

from provider_gateway_contract import content_hash, locked_authority, pin, symbols, utc

ROLE = 'GOVERNED_REALTIME_MARKET_BASELINE'
FUNCTION = 'REALTIME_BULK_QUOTES'
RETENTION = 'EPHEMERAL_ALPHA_BULK'
RADAR_SCHEMA = 'iios-alpha-opportunity-plan-v3'


def enrichment_policy():
    """This package never dispatches enrichment or confers case/order authority."""
    return {'schema': 'iios-radar-enrichment-disabled-v1',
            'alpha_additional_requests': 0, 'yahoo_additional_requests': 0,
            'other_providers': {p: {'live_dispatch': False, 'request_budget': None,
                                  'cost_budget': None, 'receipt_parent': None}
                                for p in ('ALPACA', 'BIGDATA', 'FINANCIAL_DATASETS', 'MASSIVE')},
            'alpaca': {'realtime_feed': 'iex', 'realtime_sip': False,
                       'delayed_sip_minutes': 15, 'maximum_streamed_symbols': 30,
                       'promoted_candidates_only': True},
            'authority': locked_authority()}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def plan(universe, universe_hash, calendar, calendar_hash, *, root):
    pin(universe, universe_hash)
    pin(calendar, calendar_hash)
    members = universe['symbols']
    symbols(members, count=517)  # Validate without changing independently pinned order.
    require(calendar == {'calendar': 'XNYS', 'session': '2026-09-14',
                         'open': '2026-09-14T13:30:00+00:00',
                         'close': '2026-09-14T20:00:00+00:00'}, 'SESSION_PIN')
    path = Path(root)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink(), 'DAY_ROOT')
    batches = [members[i:i + 100] for i in range(0, 517, 100)]
    checkpoints = [('OPENING', utc(calendar['open']) + timedelta(seconds=30)),
                   ('INTRADAY', utc(calendar['open']) + timedelta(hours=3)),
                   ('CLOSING', utc(calendar['close']) + timedelta(seconds=30))]
    rows = []
    for phase, target in checkpoints:
        for batch, members in enumerate(batches):
            start = target + timedelta(seconds=25 * batch)
            rows.append({'slot': len(rows), 'id': f'{phase}-{batch}', 'phase': phase,
                         'batch': batch, 'symbols': members, 'symbol_hash': content_hash(members),
                         'valid_from': start.isoformat(), 'expires_at': (start + timedelta(seconds=5)).isoformat(),
                         'root': str(path / f'{phase}-{batch}')})
    return {'schema': 'iios-alpha-bulk-plan-v1', 'provider': 'ALPHA_VANTAGE', 'role': ROLE,
            'universe': universe, 'universe_parent': universe_hash,
            'calendar': calendar, 'calendar_parent': calendar_hash, 'root': str(path),
            'rows': rows, 'maximum_requests': 18, 'maximum_batch_symbols': 100,
            'timeout_seconds': 20, 'maximum_response_bytes': 1_000_000,
            'retry_count': 0, 'authority': locked_authority()}


def radar_plan(universe, universe_hash, calendar, calendar_hash, *, root,
               opportunity_schedule, schedule_hash):
    """Explicit adapter, not an inferred conversion of a legacy plan.

    The embedded schedule is reconstructed using its independently pinned inputs.
    Its hash alone cannot supply the missing universe or calendar document.
    """
    from copy import deepcopy
    from opportunity_spine_contract import schedule
    pin(universe, universe_hash)
    pin(calendar, calendar_hash)
    pin(opportunity_schedule, schedule_hash)
    require(opportunity_schedule == schedule(universe, universe_hash, calendar, calendar_hash,
            mode='FULL_OPPORTUNITY_RADAR', root=root), 'RADAR_SCHEDULE_BINDING')
    legacy = plan(universe, universe_hash, calendar, calendar_hash, root=root)
    preflight = opportunity_schedule['preflight']
    rows = [dict(preflight)]
    for scan in opportunity_schedule['scans']:
        for batch, members in enumerate(scan['batches']):
            identifier = f"SCAN-{scan['scan']:02d}-{batch}"
            rows.append({'slot': len(rows), 'id': identifier, 'phase': 'SCAN',
                         'scan': scan['scan'], 'batch': batch, 'symbols': list(members),
                         'symbol_hash': content_hash(members), 'valid_from': scan['start'],
                         'expires_at': scan['end'], 'root': str(Path(root) / identifier)})
    legacy.update(schema=RADAR_SCHEMA, mode='FULL_OPPORTUNITY_RADAR', rows=rows,
                  opportunity_schedule=deepcopy(opportunity_schedule), schedule_parent=schedule_hash,
                  maximum_requests=475, collection_requests=474, preflight_requests=1,
                  maximum_starts_per_rolling_minute=3, requires_preflight=True,
                  response_must_finish_in_interval=True, redirects=0, pagination=0,
                  fallback=0, backfill=False, maximum_age_seconds=60,
                  finalization_deadline='2026-09-14T20:15:00+00:00',
                  enrichment=enrichment_policy())
    return deepcopy(legacy)


def verify_plan(value, expected):
    pin(value, expected)
    require(isinstance(value, dict) and 'schema' in value, 'PLAN_VERSION_REQUIRED')
    schema = value['schema']
    require(schema in ('iios-alpha-bulk-plan-v1', 'iios-alpha-session-plan-v2', RADAR_SCHEMA),
            'PLAN_VERSION_UNSUPPORTED')
    require({'universe', 'universe_parent', 'calendar', 'calendar_parent', 'root'} <= set(value),
            'PLAN_INPUTS_REQUIRED')
    if schema == RADAR_SCHEMA:
        require({'opportunity_schedule', 'schedule_parent'} <= set(value), 'RADAR_INPUTS_REQUIRED')
        rebuilt = radar_plan(value['universe'], value['universe_parent'], value['calendar'],
                             value['calendar_parent'], root=value['root'],
                             opportunity_schedule=value['opportunity_schedule'],
                             schedule_hash=value['schedule_parent'])
        require(value == rebuilt, 'PLAN_SUBSTITUTION')
        return
    builder = plan
    if schema == 'iios-alpha-session-plan-v2':
        from alpha_session_readiness import readiness_plan
        builder = readiness_plan
    require(value == builder(value['universe'], value['universe_parent'], value['calendar'],
                             value['calendar_parent'], root=value['root']), 'PLAN_SUBSTITUTION')


def admit_batch(manifest, account):
    value = account['bulk_plan']
    verify_plan(value, account['bulk_plan_parent'])
    slot = account['bulk_slot']
    require(type(slot) is int and 0 <= slot < len(value['rows']), 'SLOT_INVALID')
    row = value['rows'][slot]
    require(manifest['symbols'] == row['symbols'] and manifest['root'] == row['root'] and
            manifest['batch_id'] == row['id'] and manifest['valid_from'] == row['valid_from'] and
            manifest['expires_at'] == row['expires_at'], 'BATCH_BINDING')
    require(manifest['timeout_seconds'] == 20 and manifest['maximum_response_bytes'] == 1_000_000,
            'BULK_TRANSPORT_BOUND')
    require(account.get('qualification_parameters') == manifest['parameters'], 'BULK_ACCOUNT_FUNCTION_BINDING')
    require(account['rate_per_minute'] <= 150, 'RATE_CEILING')
    if value['schema'] == RADAR_SCHEMA:
        require(manifest['maximum_age_seconds'] == 60, 'RADAR_FRESHNESS_BOUND')
        require(utc(account['expires_at']) >= utc(value['finalization_deadline']), 'RADAR_ACCOUNT_EXPIRY')
        require(utc(account['retention']['retain_until']) >= utc(value['finalization_deadline']),
                'RADAR_RETENTION_EXPIRY')


def summarize(payload, requested, *, received_at, maximum_age_seconds):
    """Only grammar-validated symbols/timestamps and locally generated enums survive.

    Never retain prices, arbitrary provider messages, labels or a payload hash.
    Naive timestamps are preserved as provider wall times with unknown timezone.
    """
    require(isinstance(payload, dict) and set(payload) <= {'endpoint', 'message', 'data'} and
            isinstance(payload.get('data'), list), 'BULK_SCHEMA')
    require(payload.get('endpoint', FUNCTION) == FUNCTION, 'WRONG_PROVIDER_ENDPOINT')
    require(not payload.get('message'), 'PROVIDER_MESSAGE')
    require(len(payload['data']) <= 1000, 'RESPONSE_ROW_LIMIT')
    counts = Counter()
    timing, malformed = [], []
    for index, row in enumerate(payload['data']):
        if not isinstance(row, dict) or not isinstance(row.get('symbol'), str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9.-]{0,15}', row['symbol']):
            malformed.append(index)
            continue
        symbol = row['symbol']
        counts[symbol] += 1
        missing = [field for field in ('timestamp', 'open', 'high', 'low', 'close', 'volume') if row.get(field) is None]
        invalid = []
        for field in ('open', 'high', 'low', 'close', 'volume'):
            if field in missing:
                continue
            value = row[field]
            try:
                require(type(value) in (str, int, float) and not isinstance(value, bool), 'NUMBER')
                number = Decimal(str(value))
                require(number.is_finite() and number >= 0, 'NUMBER')
            except (ValueError, InvalidOperation):
                invalid.append(field)
        stamp = row.get('timestamp')
        state, retained_stamp = 'MISSING', None
        if stamp is not None:
            if isinstance(stamp, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?', stamp):
                try:
                    from datetime import datetime
                    parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                    retained_stamp = stamp
                    if parsed.tzinfo is None:
                        state = 'UNVERIFIED_TIMEZONE'
                    else:
                        age = (utc(received_at) - parsed).total_seconds()
                        state = 'FUTURE' if age < 0 else 'STALE' if age > maximum_age_seconds else 'WITHIN_AGE_BOUND'
                except ValueError:
                    state = 'MALFORMED'
            else:
                state = 'MALFORMED'
        if invalid or state == 'MALFORMED':
            malformed.append(index)
        timing.append({'symbol': symbol, 'provider_timestamp': retained_stamp, 'freshness': state,
                       'missing_fields': missing, 'invalid_fields': invalid})
    missing_symbols = [s for s in requested if s not in counts]
    duplicates = sorted(s for s, n in counts.items() if n > 1)
    unexpected = sorted(set(counts) - set(requested))
    complete = not (missing_symbols or duplicates or unexpected or malformed or any(r['missing_fields'] for r in timing))
    return {'provider': 'ALPHA_VANTAGE', 'requested_symbols': list(requested),
            'returned_symbols': [s for s in requested if s in counts],
            'missing_symbols': missing_symbols, 'duplicate_symbols': duplicates,
            'unexpected_symbols': unexpected, 'malformed_rows': malformed, 'timing': timing,
            'coverage': 'COMPLETE' if complete else 'PARTIAL',
            'freshness': 'WITHIN_AGE_BOUND' if complete and all(r['freshness'] == 'WITHIN_AGE_BOUND' for r in timing) else 'UNVERIFIED_OR_STALE',
            'response_realtime_entitlement': 'UNVERIFIED', 'atomic_snapshot': False}
