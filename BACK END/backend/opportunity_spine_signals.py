"""Deterministic in-memory signals. Prices/state have no persistence interface."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import math

from alpha_market_baseline import require
from opportunity_spine_contract import receipt, verify
from provider_gateway_contract import content_hash, pin, utc

# Proposed detection thresholds, not a replacement for existing promotion eligibility.
POLICY = {'version': 'opportunity-signals-v1', 'return_percent': 1.0, 'persistence_scans': 2,
          'maximum_promotions': 5, 'maximum_cases': 2, 'cooldown_hours': 12,
          'legacy_minimum_score': 45.0, 'legacy_minimum_news': 2, 'maximum_age_seconds': 60}


def policy(value, expected):
    pin(value, expected)
    require(value == POLICY, 'POLICY_NOT_REVIEWED')
    return deepcopy(value)


def number(value):
    if value is None:
        return None
    require(type(value) in (str, int, float), 'NUMBER_TYPE')
    try:
        d = Decimal(str(value))
        require(d.is_finite() and d >= 0, 'NUMBER_RANGE')
        f = float(d)
        require(math.isfinite(f), 'NUMBER_RANGE')
        return f
    except InvalidOperation:
        raise ValueError('NUMBER_FORMAT') from None


def change(now, prior):
    return None if now is None or prior is None or prior <= 0 else round((now/prior-1)*100, 6)


def compare_yahoo(alpha, yahoo, expected, *, scan, scan_parent, source):
    """Consume only sanitized, independently pinned challenger receipts; never fetch."""
    if yahoo is None:
        require(expected is None, 'MISSING_YAHOO_PARENT')
        return {'status': 'UNAVAILABLE', 'parent': None, 'requests': None, 'rows': [], 'receipt': None}
    data = verify(yahoo, expected, kind='yahoo', parents={'scan': scan_parent}, source=source)
    require(set(data) == {'scan', 'status', 'symbols', 'provider_timestamp', 'recorded_requests'}, 'YAHOO_SCHEMA')
    require(data['scan'] == scan and data['status'] in ('PASS', 'FAILED', 'UNAVAILABLE'), 'YAHOO_CYCLE')
    require(type(data['recorded_requests']) is int and data['recorded_requests'] >= 0, 'YAHOO_USAGE')
    symbols = data['symbols']
    require(isinstance(symbols, list) and len(set(symbols)) == len(symbols), 'YAHOO_DUPLICATE')
    from provider_gateway_contract import symbols as validate_symbols
    if symbols:
        validate_symbols(symbols, count=len(symbols))
    stamp = data['provider_timestamp']
    if stamp is not None:
        utc(stamp)  # No inferred timestamp, timezone, or freshness.
    rows = []
    if data['status'] == 'PASS':
        for s in sorted(set(alpha) | set(symbols)):
            rows.append({'symbol': s, 'comparison': 'AGREEMENT' if s in alpha and s in symbols else
                         'ALPHA_ONLY' if s in alpha else 'YAHOO_ONLY_ALPHA_EVIDENCE_REQUIRED',
                         'provider_timestamp': stamp})
    return {'status': data['status'], 'parent': expected, 'requests': data['recorded_requests'],
            'timestamp_status': 'MISSING' if stamp is None else 'PRESENT_NOT_FRESHNESS_PROOF', 'rows': rows, 'receipt': deepcopy(yahoo)}


class Signals:
    """Only receives payloads through the same OfflineSession admission operation.

    Retains ephemeral numeric state for this instance only. Optional upstream fields
    are validated individually; absence never turns into zero. External benchmark/
    sector histories are not fabricated when SPY/QQQ or governed sector data is absent.
    """
    def __init__(self, config, config_hash, *, sectors=None, sectors_hash=None):
        self.config = policy(config, config_hash)
        self.config_hash = config_hash
        require((sectors is None) == (sectors_hash is None), "SECTOR_PIN_REQUIRED")
        if sectors is not None:
            pin(sectors, sectors_hash)
            import re
            require(set(sectors) == {"version", "members"} and sectors["version"] == "governed-sectors-v1", "SECTOR_SCHEMA")
            require(all(re.fullmatch("[A-Z0-9.-]{1,16}", k) and re.fullmatch("[A-Z_]{1,40}", v) for k,v in sectors["members"].items()), "SECTOR_MEMBERS")
        self.sectors, self.sectors_hash = deepcopy(sectors), sectors_hash
        self.history, self.pending, self.parents = {}, {}, []
        self.last_scan = -1

    def consume(self, session, payload, *, response_at, reservation_hash):
        require(session.pending is not None, 'NO_ADMISSION')
        scan = session.pending['data']['scan']
        result = session.complete(payload, response_at=response_at, reservation_hash=reservation_hash)
        if result['data']['status'] != 'PASS':
            self.pending = {}
            return result, None
        if scan < 0:
            return result, None
        require(scan == self.last_scan+1, 'SIGNAL_SCAN_SEQUENCE')
        self.parents.append(content_hash(result))
        for row in payload['data']:
            s = row['symbol']
            require(s not in self.pending, 'SIGNAL_DUPLICATE')
            fields = {}
            for k in ('open', 'high', 'low', 'close', 'volume', 'previous_close', 'average_volume'):
                try:
                    fields[k] = number(row.get(k))
                except ValueError:
                    fields[k] = None
            fields['timestamp'] = row['timestamp']
            self.pending[s] = fields
        if result['data']['batch'] != 5:
            return result, None
        require(len(self.pending) == 517, 'SIGNAL_PARTIAL_SCAN')
        rows = []
        for s, current in self.pending.items():
            old = self.history.get(s)
            close = current['close']
            previous = old['last'] if old else None
            opening = old['opening'] if old else current['open']
            five = change(close, previous) if session.plan['mode'] == 'FULL_OPPORTUNITY_RADAR' else None
            session_return = change(close, opening)
            acceleration = None if five is None or old is None or old['return'] is None else round(five-old['return'], 6)
            reversal = None if five is None or old is None or old['return'] is None else five*old['return'] < 0
            detected = five is not None and abs(five) >= self.config['return_percent']
            persistence = (old['persistence']+1 if old and old['return'] is not None and five*old['return'] > 0 else 1) if detected else 0
            high = max(current['high'], old['high']) if old else current['high']
            low = min(current['low'], old['low']) if old else current['low']
            spread = change(current['high'], current['low'])
            expansion = None if old is None or old['spread'] is None or spread is None else spread > old['spread']
            opening_high = old['opening_high'] if old else current['high']
            opening_low = old['opening_low'] if old else current['low']
            rows.append({'symbol': s, 'provider_timestamp': current['timestamp'], 'freshness': 'WITHIN_AGE_BOUND',
                         'gap_percent': change(current['open'], current['previous_close']),
                         'five_minute_return_percent': five if session.plan['mode'] == 'FULL_OPPORTUNITY_RADAR' else None,
                         'session_return_percent': session_return, 'acceleration': acceleration,
                         'reversal': reversal, 'volume_change_percent': change(current['volume'], old['volume'] if old else None),
                         'relative_volume': None if not current['average_volume'] else round(current['volume']/current['average_volume'], 6),
                         'volatility_expansion': expansion,
                         'opening_range_movement': 'ABOVE' if close > opening_high else 'BELOW' if close < opening_low else 'WITHIN',
                         'session_high': close == high, 'session_low': close == low,
                         'relative_strength_spy': None, 'relative_strength_qqq': None, 'sector_divergence': None,
                         'persistence': persistence, 'detected': detected,
                         'persistent': persistence >= self.config['persistence_scans'],
                         'warnings': [k for k in ('previous_close', 'average_volume') if current[k] is None] + ['GOVERNED_SECTOR_DATA_UNAVAILABLE']})
            self.history[s] = {'last': close, 'opening': opening, 'return': five, 'persistence': persistence,
                               'high': high, 'low': low, 'spread': spread, 'volume': current['volume'],
                               'opening_high': opening_high, 'opening_low': opening_low}
        returns = {r['symbol']: r['session_return_percent'] for r in rows}
        for row in rows:
            for ticker, field in [('SPY', 'relative_strength_spy'), ('QQQ', 'relative_strength_qqq')]:
                if returns.get(ticker) is not None and row['session_return_percent'] is not None:
                    row[field] = round(row['session_return_percent']-returns[ticker], 6)
                else:
                    row['warnings'].append(ticker+'_UNAVAILABLE')
        if self.sectors is not None:
            mapping = self.sectors['members']
            require(set(mapping) <= set(returns), 'SECTOR_UNIVERSE_SUBSTITUTION')
            for row in rows:
                sector = mapping.get(row['symbol'])
                peers = [v for k,v in returns.items() if k != row['symbol'] and mapping.get(k) == sector and v is not None] if sector else []
                if peers and row['session_return_percent'] is not None:
                    row['sector_divergence'] = round(row['session_return_percent']-sum(peers)/len(peers), 6)
                    row['warnings'].remove('GOVERNED_SECTOR_DATA_UNAVAILABLE')
        signals = receipt('signals', {'scan': scan, 'mode': session.plan['mode'], 'rows': rows},
                          {'schedule': session.parent, 'policy': self.config_hash,
                           **({'sectors': self.sectors_hash} if self.sectors_hash else {}),
                           **{str(i): h for i, h in enumerate(self.parents)}}, source=session.source)
        self.pending, self.parents, self.last_scan = {}, [], scan
        return result, signals


class Promotions:
    def __init__(self, config, config_hash):
        self.config = policy(config, config_hash)
        self.config_hash, self.seen = config_hash, {}

    def select(self, signals, expected, *, parents, eligibility, eligibility_hash, source, now):
        data = verify(signals, expected, kind='signals', parents=parents, source=source)
        admissions = verify(eligibility, eligibility_hash, kind='legacy-promotion', parents={'signals': expected}, source=source)
        require(set(admissions) == {'rows'}, 'PROMOTION_SCHEMA')
        require(len({r['symbol'] for r in admissions['rows']}) == len(admissions['rows']), 'PROMOTION_DUPLICATE')
        scores = {r['symbol']: r for r in admissions['rows']}
        require(set(scores) <= {r['symbol'] for r in data['rows']}, 'PROMOTION_SUBSTITUTION')
        chosen = []
        for row in data['rows']:
            s = row['symbol']; gate = scores.get(s)
            if not gate or not row['detected']:
                continue
            require(set(gate) == {'symbol', 'score', 'news_count', 'quote_ok', 'eligible_for_promotion'}, 'LEGACY_GATE_SCHEMA')
            require(type(gate['score']) in (int, float) and math.isfinite(gate['score']) and
                    type(gate['news_count']) is int and gate['news_count'] >= 0, 'LEGACY_GATE_VALUES')
            if not (gate['quote_ok'] is True and gate['eligible_for_promotion'] is True and
                    gate['score'] >= 45 and gate['news_count'] >= 2):
                continue
            previous = self.seen.get(s)
            if previous is not None:
                require(utc(now) >= utc(previous), 'PROMOTION_CLOCK_ROLLBACK')
                if (utc(now)-utc(previous)).total_seconds() < self.config['cooldown_hours']*3600:
                    continue
            if len(chosen) < self.config['maximum_promotions']:
                chosen.append({'symbol': s, 'candidate_id': content_hash([expected, s]),
                               'case_selected': len(chosen) < self.config['maximum_cases']})
                self.seen[s] = now
        return receipt('candidates', {'scan': data['scan'], 'rows': chosen},
                       {'signals': expected, 'eligibility': eligibility_hash, 'policy': self.config_hash}, source=source)
