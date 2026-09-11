"""Pure, offline Opportunity Spine admission. No transport, storage or activation."""
from copy import deepcopy
from datetime import timedelta
import re

from alpha_market_baseline import require, summarize
from alpha_session_readiness import readiness_plan
from provider_gateway_contract import content_hash, pin, utc

FLAGS = ('broker_connected', 'paper_order_permission', 'trade_execution_permission',
         'live_execution', 'ledger_write_authority')
MODES = ('BASELINE_ONLY', 'FULL_OPPORTUNITY_RADAR')
STATES = ('REQUIRED', 'OPTIONAL', 'NOT_RUN', 'PASS', 'FAILED', 'BLOCKED', 'UNAVAILABLE')


def authority():
    return dict.fromkeys(FLAGS, False)


def receipt(kind, data, parents, *, source):
    require(bool(re.fullmatch('[0-9a-f]{40}', source)), 'SOURCE_IDENTITY')
    require(all(re.fullmatch('[0-9a-f]{64}', p) for p in parents.values()), 'PARENT_HASH')
    value = {'schema': 'iios-opportunity-spine-v1', 'kind': kind, 'scope': 'OFFLINE_TEST',
             'source_commit': source, 'runtime_identity': None, 'session_authority': None,
             'authority': authority(), 'parents': dict(parents), 'data': deepcopy(data)}
    return {**value, 'receipt_hash': content_hash(value)}


def verify(value, expected, *, kind, parents, source):
    pin(value, expected)
    body = {k: v for k, v in value.items() if k != 'receipt_hash'}
    require(set(value) == {'schema', 'kind', 'scope', 'source_commit', 'runtime_identity',
                          'session_authority', 'authority', 'parents', 'data', 'receipt_hash'}, 'RECEIPT_SCHEMA')
    require(value['receipt_hash'] == content_hash(body), 'RECEIPT_SELF_HASH')
    require(value['kind'] == kind and value['source_commit'] == source and value['parents'] == parents,
            'RECEIPT_IDENTITY_OR_PARENT')
    require(value['schema'] == 'iios-opportunity-spine-v1' and value['scope'] == 'OFFLINE_TEST'
            and value['runtime_identity'] is None and value['session_authority'] is None, 'OFFLINE_ONLY')
    require(set(value['authority']) == set(FLAGS) and all(value['authority'][f] is False for f in FLAGS), 'AUTHORITY')
    return deepcopy(value['data'])


def schedule(universe, universe_hash, calendar, calendar_hash, *, mode, root):
    require(mode in MODES, 'EXPLICIT_MODE_REQUIRED')
    baseline = readiness_plan(universe, universe_hash, calendar, calendar_hash, root=root)
    if mode == 'BASELINE_ONLY':
        scans = [{'scan': i, 'start': baseline['rows'][1 + i * 6]['valid_from'],
                  'end': baseline['rows'][1 + i * 6]['expires_at']} for i in range(3)]
    else:
        first = utc(calendar['open']) + timedelta(seconds=30)
        scans = [{'scan': i, 'start': (first + timedelta(minutes=5*i)).isoformat(),
                  'end': (first + timedelta(minutes=5*(i+1))).isoformat()} for i in range(79)]
    for scan in scans:
        scan['batches'] = [universe['symbols'][i:i+100] for i in range(0, 517, 100)]
        scan['batch_hashes'] = [content_hash(b) for b in scan['batches']]
    return {'version': 'opportunity-schedule-v1', 'session': '2026-09-14', 'mode': mode,
            'baseline_parent': content_hash(baseline), 'universe_parent': universe_hash,
            'calendar_parent': calendar_hash, 'preflight': baseline['rows'][0], 'scans': scans,
            'collection_requests': len(scans)*6, 'proposed_request_ceiling': 1+len(scans)*6,
            'maximum_starts_per_rolling_minute': 3, 'timeout_seconds': 20,
            'maximum_response_bytes': 1_000_000, 'retries': 0, 'redirects': 0,
            'pagination': 0, 'fallback': 0, 'backfill': False, 'atomic_snapshot': False,
            'allowance_released': False, 'authority': authority()}


class OfflineSession:
    """Single-use reservations. An interrupted or failed batch irreversibly stops this instance.

    This class never dispatches. Native recovery and live admission remain unavailable.
    Payloads are inspected in memory; returned receipts never include provider payload hashes.
    """
    def __init__(self, plan, expected, *, universe, universe_hash, calendar, calendar_hash, root, source):
        pin(plan, expected)
        require(plan == schedule(universe, universe_hash, calendar, calendar_hash,
                                mode=plan['mode'], root=root), 'PLAN_SUBSTITUTION')
        self.plan, self.source, self.parent = deepcopy(plan), source, expected
        self.slot, self.pending, self.stopped = 0, None, False
        self.starts, self.receipts, self.phase_rows = [], [], []

    def _row(self):
        if self.slot == 0:
            p = self.plan['preflight']
            return -1, 0, p['valid_from'], p['expires_at'], p['symbols']
        scan, batch = divmod(self.slot-1, 6)
        row = self.plan['scans'][scan]
        return scan, batch, row['start'], row['end'], row['batches'][batch]

    def reserve(self, dispatch_at):
        require(not self.stopped and self.pending is None, 'INTERRUPTED_OR_STOPPED')
        require(self.slot < self.plan['proposed_request_ceiling'], 'REQUEST_CEILING')
        scan, batch, start, end, symbols = self._row()
        now = utc(dispatch_at)
        if not utc(start) <= now < utc(end):
            self.stopped = True
            raise ValueError('CYCLE_DEADLINE_NO_BACKFILL')
        require(not self.starts or now >= utc(self.starts[-1]), 'CLOCK_ROLLBACK')
        require(sum((now-utc(t)).total_seconds() < 60 for t in self.starts) < 3, 'ROLLING_RATE')
        previous = content_hash(self.receipts[-1]) if self.receipts else self.parent
        self.pending = receipt('reservation', {'slot': self.slot, 'scan': scan, 'batch': batch,
                               'symbols': symbols, 'dispatch_at': dispatch_at, 'deadline': end},
                               {'schedule': self.parent, 'previous': previous}, source=self.source)
        self.starts.append(dispatch_at)
        return deepcopy(self.pending)

    def complete(self, payload, *, response_at, reservation_hash):
        require(self.pending is not None and not self.stopped, 'NO_PENDING_RESERVATION')
        pin(self.pending, reservation_hash)
        row = self.pending['data']
        checks, reason = None, None
        try:
            require(utc(row['dispatch_at']) <= utc(response_at) < utc(row['deadline']), 'INTERVAL_OR_CLOCK')
            require((utc(response_at)-utc(row['dispatch_at'])).total_seconds() <= 20, 'RESPONSE_TIMEOUT')
            # Encoded size is measured without retaining or hashing provider bytes.
            import json
            require(len(json.dumps(payload).encode()) <= 1_000_000, 'RESPONSE_SIZE')
            checks = summarize(payload, row['symbols'], received_at=response_at, maximum_age_seconds=60)
            require(checks['coverage'] == 'COMPLETE' and checks['freshness'] == 'WITHIN_AGE_BOUND', 'COVERAGE_OR_FRESHNESS')
            require([r['symbol'] for r in payload['data']] == row['symbols'], 'REORDERED_RESPONSE')
        except (ValueError, TypeError, KeyError):
            reason = 'AMBIGUOUS_OR_INVALID_BATCH'
            self.stopped = True
        result = receipt('batch', {'slot': row['slot'], 'scan': row['scan'], 'batch': row['batch'],
                         'dispatch_at': row['dispatch_at'], 'response_at': response_at, 'checks': checks,
                         'status': 'FAILED' if reason else 'PASS', 'failure': reason,
                         'reservation_consumed': True, 'billing': 'UNVERIFIED', 'retry_count': 0},
                         {'schedule': self.parent, 'reservation': reservation_hash}, source=self.source)
        self.receipts.append(result)
        self.slot += 1
        self.pending = None
        return deepcopy(result)

    def interrupt(self):
        self.stopped = True
        return receipt('interruption', {'reserved': len(self.starts), 'completed': len(self.receipts),
                       'ambiguous_reservation_retained': self.pending is not None, 'retry_count': 0},
                       {'schedule': self.parent}, source=self.source)

    def final(self):
        complete = not self.stopped and self.pending is None and self.slot == self.plan['proposed_request_ceiling']
        return receipt('collection', {'mode': self.plan['mode'], 'status': 'PASS' if complete else 'FAILED',
                       'reserved_requests': len(self.starts), 'completed_requests': len(self.receipts),
                       'receipts': deepcopy(self.receipts), 'atomic_snapshot': False},
                       {'schedule': self.parent}, source=self.source)
