import copy
import json
from pathlib import Path
import tempfile
import os
import unittest

from alpha_market_baseline import plan, verify_plan, summarize, FUNCTION, ROLE, RETENTION
from provider_gateway_contract import content_hash
from provider_gateway_live_contract import request_parameters
from provider_gateway_qualification import qualify
from test_provider_gateway_live_contract import quote_fixture, repin
from test_provider_gateway_credentials import FakeCredentials, FAKE
from test_provider_gateway_transport import FakeNetwork
from alpha_market_baseline import radar_plan, RADAR_SCHEMA

CALENDAR = {'calendar': 'XNYS', 'session': '2026-09-14', 'open': '2026-09-14T13:30:00+00:00', 'close': '2026-09-14T20:00:00+00:00'}


def radar_fixture_plan():
    from opportunity_spine_contract import schedule
    root = tempfile.mkdtemp(prefix='radar-', dir=os.environ['IIOS_GATEWAY_TEST_ROOT'])
    universe = {'symbols': [f'S{i:03}' for i in reversed(range(517))]}
    s = schedule(universe, content_hash(universe), CALENDAR, content_hash(CALENDAR),
                 mode='FULL_OPPORTUNITY_RADAR', root=root)
    return radar_plan(universe, content_hash(universe), CALENDAR, content_hash(CALENDAR),
                      root=root, opportunity_schedule=s, schedule_hash=content_hash(s))


class RadarPlanTests(unittest.TestCase):
    def test_explicit_adapter_admits_all_475_with_original_schedule_pin(self):
        p = radar_fixture_plan()
        verify_plan(p, content_hash(p))
        self.assertEqual(p['schema'], RADAR_SCHEMA)
        self.assertEqual(p['maximum_requests'], 475)
        self.assertEqual(len(p['rows']), 475)
        self.assertEqual(len(p['rows'][0]['symbols']), 10)
        self.assertEqual(p['schedule_parent'], content_hash(p['opportunity_schedule']))
        self.assertEqual(p['rows'][0]['valid_from'], '2026-09-14T13:20:00+00:00')
        self.assertEqual(p['rows'][0]['expires_at'], '2026-09-14T13:25:00+00:00')
        for i in range(79):
            rows = p['rows'][1+i*6:7+i*6]
            self.assertEqual([len(r['symbols']) for r in rows], [100]*5+[17])
            self.assertEqual(sum([r['symbols'] for r in rows], []), p['universe']['symbols'])
            self.assertEqual({r['scan'] for r in rows}, {i})
        self.assertEqual(p['rows'][-1]['expires_at'], '2026-09-14T20:05:30+00:00')
        self.assertEqual(p['finalization_deadline'], '2026-09-14T20:15:00+00:00')

    def test_missing_unknown_or_inferred_version_rejected_cleanly(self):
        p = radar_fixture_plan()
        for field in ('schema', 'universe', 'schedule_parent'):
            bad = copy.deepcopy(p);del bad[field]
            with self.subTest(field=field), self.assertRaises(ValueError):verify_plan(bad, content_hash(bad))
        for schema in ('unknown', 'iios-alpha-session-plan-v2', 'iios-alpha-bulk-plan-v1'):
            bad = {**p, 'schema': schema}
            with self.subTest(schema=schema), self.assertRaises(ValueError):verify_plan(bad, content_hash(bad))
        # The formerly crashing bare offline schedule lacks runtime input bindings.
        s = p['opportunity_schedule']
        with self.assertRaisesRegex(ValueError, 'PLAN_VERSION_REQUIRED'):verify_plan(s, content_hash(s))

    def test_universe_missing_duplicate_extra_reorder_substitution_and_hash(self):
        p = radar_fixture_plan()
        for kind in ('missing', 'extra', 'duplicate', 'reordered', 'substituted', 'hash'):
            bad = copy.deepcopy(p);members = bad['universe']['symbols']
            if kind == 'missing':members.pop()
            elif kind == 'extra':members.append('EXTRA')
            elif kind == 'duplicate':members[-1] = members[0]
            elif kind == 'reordered':members.reverse()
            elif kind == 'substituted':members[0] = 'OTHER'
            else:bad['universe_parent'] = '0'*64
            with self.subTest(kind=kind), self.assertRaises(ValueError):verify_plan(bad, content_hash(bad))
        bad = copy.deepcopy(p);bad['universe']['symbols'].reverse()
        bad['universe_parent'] = content_hash(bad['universe'])
        with self.assertRaises(ValueError):verify_plan(bad, content_hash(bad))

    def test_batch_order_membership_slot_and_independent_plan_hash(self):
        p = radar_fixture_plan()
        for change in ('order', 'missing', 'extra', 'duplicate', 'slot', 'batch_hash'):
            bad = copy.deepcopy(p)
            if change == 'order':bad['rows'][1]['symbols'].reverse()
            elif change == 'missing':bad['rows'].pop()
            elif change == 'extra':bad['rows'].append(copy.deepcopy(bad['rows'][-1]))
            elif change == 'duplicate':bad['rows'][2] = copy.deepcopy(bad['rows'][1])
            elif change == 'slot':bad['rows'][1]['slot'] = 0
            else:bad['rows'][1]['symbol_hash'] = '0'*64
            with self.subTest(change=change), self.assertRaises(ValueError):verify_plan(bad, content_hash(bad))
        with self.assertRaises(ValueError):verify_plan(p, '0'*64)

    def test_timing_count_and_budget_constraints_cannot_be_relabelled(self):
        p = radar_fixture_plan()
        changes = {'maximum_requests': 476, 'collection_requests': 475,
                   'maximum_starts_per_rolling_minute': 4, 'timeout_seconds': 21,
                   'maximum_response_bytes': 1000001, 'maximum_age_seconds': 61,
                   'retry_count': 1, 'redirects': 1, 'pagination': 1, 'fallback': 1,
                   'backfill': True, 'finalization_deadline': '2026-09-14T20:16:00+00:00'}
        for key, value in changes.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                bad = {**p, key: value};verify_plan(bad, content_hash(bad))
        for provider in ('ALPACA', 'BIGDATA', 'FINANCIAL_DATASETS', 'MASSIVE'):
            bad = copy.deepcopy(p);bad['enrichment']['other_providers'][provider]['live_dispatch'] = True
            with self.assertRaises(ValueError):verify_plan(bad, content_hash(bad))
        for key in ('alpha_additional_requests', 'yahoo_additional_requests'):
            bad = copy.deepcopy(p);bad['enrichment'][key] = 1
            with self.assertRaises(ValueError):verify_plan(bad, content_hash(bad))
        self.assertEqual(p['enrichment']['alpaca']['maximum_streamed_symbols'], 30)
        self.assertFalse(p['enrichment']['alpaca']['realtime_sip'])


class BulkTests(unittest.TestCase):
    def setup_plan(self):
        self.day = Path(tempfile.mkdtemp(prefix='day-', dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        self.universe = {'symbols': [f'S{i:03}' for i in reversed(range(517))]}
        self.plan = plan(self.universe, content_hash(self.universe), CALENDAR, content_hash(CALENDAR), root=str(self.day))
        for row in self.plan['rows']:
            Path(row['root']).mkdir(mode=0o700)
        return self.plan

    def docs(self, slot=0):
        m, a, r = quote_fixture()
        row = self.plan['rows'][slot]
        m.update(role=ROLE, endpoint=FUNCTION, feed='real_time', symbols=row['symbols'], root=row['root'], batch_id=row['id'],
                 valid_from=row['valid_from'], expires_at=row['expires_at'], timeout_seconds=20,
                 maximum_response_bytes=1_000_000)
        m['parameters'] = request_parameters('ALPHA_VANTAGE', m['symbols'], 'real_time', function=FUNCTION)
        a.update(endpoint=FUNCTION, feed='real_time', symbols=m['symbols'], qualification_parameters=m['parameters'], bulk_plan=self.plan,
                 bulk_plan_parent=content_hash(self.plan), bulk_slot=slot)
        a['retention'].update(mode=RETENTION, raw_body=False, normalized=False, references=False,
                              hashes=False, sanitized_receipt=True)
        repin(m, a, r)
        return m, a, r

    def payload(self, slot=0):
        row = self.plan['rows'][slot]
        return {'data': [{'symbol': symbol, 'timestamp': row['valid_from'], 'open': '17.123456',
                          'high': '18', 'low': '16', 'close': '17.5', 'volume': '12'} for symbol in row['symbols']]}

    def execute(self, slot=0, payload=None, previous=None, **kwargs):
        m, a, r = self.docs(slot)
        network = FakeNetwork(payload=self.payload(slot) if payload is None else payload, **kwargs)
        receipt = qualify(m, a, r, expected=repin(m, a, r), credential_backend=FakeCredentials(),
                          network=network, clock=lambda: m['valid_from'], expected_bulk_previous=previous)
        return receipt, network

    def test_517_order_six_batches_eighteen_rows(self):
        p = self.setup_plan()
        verify_plan(p, content_hash(p))
        self.assertEqual([len(r['symbols']) for r in p['rows'][:6]], [100]*5+[17])
        self.assertEqual(sum((r['symbols'] for r in p['rows'][:6]), []), self.universe['symbols'])
        self.assertEqual(len(p['rows']), 18)
        self.assertEqual(p['rows'][6]['valid_from'], '2026-09-14T16:30:00+00:00')
        self.assertEqual(p['rows'][12]['valid_from'], '2026-09-14T20:00:30+00:00')

    def test_bad_universe_or_pin_rejected(self):
        self.setup_plan()
        for n in (516, 518):
            u = {'symbols': [f'S{i}' for i in range(n)]}
            with self.assertRaises(ValueError):
                plan(u, content_hash(u), CALENDAR, content_hash(CALENDAR), root=str(self.day))
        with self.assertRaises(ValueError):
            plan(self.universe, '0'*64, CALENDAR, content_hash(CALENDAR), root=str(self.day))

    def test_duplicate_universe_rejected(self):
        self.setup_plan()
        self.universe['symbols'][-1] = self.universe['symbols'][0]
        with self.assertRaises(ValueError):
            plan(self.universe, content_hash(self.universe), CALENDAR, content_hash(CALENDAR), root=str(self.day))

    def test_hundred_and_one_rejected(self):
        with self.assertRaises(ValueError):
            request_parameters('ALPHA_VANTAGE', [f'S{i}' for i in range(101)], 'real_time', function=FUNCTION)

    def test_success_no_prices_or_raw_hashes(self):
        self.setup_plan()
        receipt, network = self.execute()
        self.assertEqual(network.calls, 1)
        self.assertEqual(receipt['bulk_checks']['coverage'], 'COMPLETE')
        self.assertEqual(receipt['bulk_checks']['freshness'], 'WITHIN_AGE_BOUND')
        for key in ('raw_response_sha256', 'normalized_sha256', 'observations'):
            self.assertIsNone(receipt[key])
        for p in Path(self.plan['rows'][0]['root']).iterdir():
            self.assertNotIn(b'17.123456', p.read_bytes())
            self.assertNotIn(FAKE, p.read_bytes())
        self.assertFalse(list(self.day.rglob('*.response.json')))

    def test_missing_duplicate_unexpected_and_malformed_reported(self):
        self.setup_plan()
        payload = self.payload(); payload['data'].pop()
        payload['data'].append(copy.deepcopy(payload['data'][0]))
        payload['data'].append({'symbol': 'UNEXPECTED'})
        payload['data'].append({'symbol': 'private address with spaces'})
        receipt, _ = self.execute(payload=payload)
        summary = receipt['bulk_checks']
        self.assertEqual(len(summary['missing_symbols']), 1)
        self.assertEqual(len(summary['duplicate_symbols']), 1)
        self.assertEqual(summary['unexpected_symbols'], ['UNEXPECTED'])
        self.assertTrue(summary['malformed_rows'])
        self.assertEqual(receipt['result'], 'AMBIGUOUS_OR_UNVERIFIED_STOP')
        self.assertNotIn('private address', json.dumps(receipt))

    def test_stale_future_naive_and_missing_timestamps(self):
        self.setup_plan()
        for stamp, expected in [('2026-09-10T13:30:00Z','STALE'), ('2026-09-15T13:30:00Z','FUTURE'), ('2026-09-14 13:30:30','UNVERIFIED_TIMEZONE'), (None,'MISSING')]:
            payload = self.payload();payload['data'][0]['timestamp'] = stamp
            s = summarize(payload, self.plan['rows'][0]['symbols'], received_at=self.plan['rows'][0]['valid_from'], maximum_age_seconds=60)
            self.assertEqual(s['timing'][0]['freshness'], expected)
            self.assertEqual(s['freshness'], 'UNVERIFIED_OR_STALE')

    def test_provider_error_or_foreign_schema_stops(self):
        for payload in ({'Note': 'throttle'}, {'tickers': []}, {'data': 'bad'}, {'data': [{'symbol':'S516', 'close': 'NaN'}]}):
            self.setup_plan();receipt, network = self.execute(payload=payload)
            self.assertEqual(network.calls, 1)
            self.assertEqual(receipt['result'], 'AMBIGUOUS_OR_UNVERIFIED_STOP')

    def test_response_limit_and_redirect_zero_retry(self):
        for args in ({'raw': b'x'*1_000_001}, {'status':302}, {'status':429}, {'failure':True}):
            self.setup_plan(); receipt, network = self.execute(**args)
            self.assertEqual(network.calls,1)
            self.assertEqual(receipt['result'], 'AMBIGUOUS_OR_UNVERIFIED_STOP')

    def test_full_day_exactly_eighteen_with_independent_continuation(self):
        self.setup_plan(); previous = None; total = 0
        for slot in range(18):
            receipt, network = self.execute(slot, previous=previous)
            self.assertEqual(receipt['result'], 'OBSERVED');total += network.calls
            previous = content_hash(json.loads((self.day/f'{slot}.complete.json').read_text()))
        self.assertEqual(total,18)
        with self.assertRaises(ValueError): self.execute(17, previous=previous)

    def test_missing_wrong_parent_or_slot_skip_rejected(self):
        self.setup_plan();self.execute()
        for previous in (None,'0'*64):
            with self.assertRaises(ValueError):self.execute(1,previous=previous)
        with self.assertRaises(ValueError):self.execute(2,previous='0'*64)

    def test_interrupted_reservation_never_recovered_to_dispatch(self):
        self.setup_plan()
        (self.day/'0.reserved.json').write_text('{}')
        for slot in (0,1):
            with self.assertRaises(ValueError):self.execute(slot)
        self.assertEqual((self.day/'0.reserved.json').read_text(),'{}')

    def test_partial_prior_batch_blocks_continuation(self):
        self.setup_plan(); self.execute(payload={'data':[]})
        previous=content_hash(json.loads((self.day/'0.complete.json').read_text()))
        with self.assertRaises(ValueError):self.execute(1,previous=previous)

    def test_plan_or_root_substitution_rejected(self):
        self.setup_plan();m,a,r=self.docs()
        m['root']=str(self.day)
        with self.assertRaises(ValueError):
            qualify(m,a,r,expected=repin(m,a,r),credential_backend=FakeCredentials(),network=FakeNetwork(),clock=lambda:m['valid_from'])

    def test_missed_opening_not_backfilled(self):
        self.setup_plan();m,a,r=self.docs();network=FakeNetwork()
        with self.assertRaises(ValueError):
            qualify(m,a,r,expected=repin(m,a,r),credential_backend=FakeCredentials(),network=network,clock=lambda:'2026-09-14T13:31:00Z')
        self.assertEqual(network.calls,0)

    def test_direct_executor_without_day_permit_rejected(self):
        from provider_gateway_qualification import _qualify
        self.setup_plan();m,a,r=self.docs();net=FakeNetwork()
        with self.assertRaises(ValueError):
            _qualify(m,a,r,expected=repin(m,a,r),credential_backend=FakeCredentials(),network=net,clock=lambda:m['valid_from'])
        self.assertEqual(net.calls,0)

    def test_prior_receipt_tamper_blocks_continuation(self):
        self.setup_plan();self.execute()
        previous=content_hash(json.loads((self.day/'0.complete.json').read_text()))
        receipt=Path(self.plan['rows'][0]['root'])/'ALPHA_VANTAGE.receipt.json'
        receipt.chmod(0o600);receipt.write_text('{}');receipt.chmod(0o400)
        with self.assertRaises(ValueError):self.execute(1,previous=previous)

    def test_bulk_cannot_enable_retained_data_or_trading(self):
        for key in ('retention','authority','provider'):
            self.setup_plan();m,a,r=self.docs();net=FakeNetwork()
            if key=='retention':a['retention']['mode']='RETAIN_PROVIDER_DATA'
            elif key=='authority':m['authority']['live_execution']=True
            else:m['provider']='MASSIVE'
            with self.assertRaises(ValueError):
                qualify(m,a,r,expected=repin(m,a,r),credential_backend=FakeCredentials(),network=net,clock=lambda:m['valid_from'])
            self.assertEqual(net.calls,0)

    def test_secret_echo_and_provider_free_text_never_persisted(self):
        self.setup_plan();payload=self.payload();payload['data'][0]['note']=FAKE.decode()
        receipt,net=self.execute(payload=payload)
        self.assertEqual(net.calls,1)
        self.assertEqual(receipt['result'],'AMBIGUOUS_OR_UNVERIFIED_STOP')
        for p in self.day.rglob('*.json'):self.assertNotIn(FAKE,p.read_bytes())

    def test_rolling_minute_peak_and_deadline_span(self):
        from provider_gateway_contract import utc
        self.setup_plan();times=[utc(r['valid_from']).timestamp() for r in self.plan['rows']]
        self.assertEqual(max(sum(t<=s<t+60 for s in times) for t in times),3)
        self.assertEqual(times[5]-times[0]+5+20,150)
