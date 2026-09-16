"""Synthetic planning inputs only; no provider, native process or file writes."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest

from alpha_session_contract import SCHEMA, CALENDAR_SCHEMA
from alpha_session_integration import session_plan, verify_session_plan, offline_stage_join, SCOPE
from alpha_session_readiness import STAGES, FLAGS
from provider_gateway_contract import content_hash, locked_authority, PILOT
from truth_spine_session import exchange_session


class IntegrationTests(unittest.TestCase):
    def prepare(self, day='2026-09-16'):
        spine = exchange_session(day)
        self.spine = spine.record()
        self.calendar = dict(schema=CALENDAR_SCHEMA, exchange='XNYS', timezone='America/New_York',
                             session=day, open=spine.open_at.isoformat(), close=spine.close_at.isoformat(),
                             review_parent='b'*64)
        self.universe = [f'S{i:03}' for i in range(517)]
        self.contract = dict(schema=SCHEMA, source_commit='a'*40, session=day,
                             calendar_parent=content_hash(self.calendar), universe_parent=content_hash(self.universe),
                             valid_from=spine.start.isoformat(), expires_at=spine.reconcile_end.isoformat(),
                             authority=locked_authority())
        self.now = spine.start
        self.repin()

    def setUp(self): self.prepare()

    def repin(self):
        self.contract['calendar_parent'] = content_hash(self.calendar)
        self.contract['universe_parent'] = content_hash(self.universe)
        self.expected = dict(session=content_hash(self.contract), calendar=content_hash(self.calendar),
                             universe=content_hash(self.universe), truth_spine_session=content_hash(self.spine))

    def args(self):
        return dict(expected=self.expected, now=self.now, source_commit='a'*40)

    def build(self):
        return session_plan(self.contract, self.calendar, self.universe, self.spine, **self.args())

    def verify(self, plan):
        return verify_session_plan(plan, content_hash(plan), self.contract, self.calendar,
                                   self.universe, self.spine, **self.args())

    def join(self, plan, evidence, pins):
        return offline_stage_join(plan, content_hash(plan), evidence, pins, contract=self.contract,
                                  calendar=self.calendar, universe=self.universe,
                                  spine_session=self.spine, **self.args())

    def chain(self, plan):
        evidence, pins, previous = {}, {}, None
        for stage in STAGES:
            value = dict(stage=stage, session=plan['session'], scope=SCOPE, source_commit='a'*40,
                         plan_parent=content_hash(plan), previous=previous, result='PASS',
                         authority=dict.fromkeys(FLAGS, False))
            evidence[stage], pins[stage] = value, content_hash(value)
            previous = pins[stage]
        return evidence, pins

    def test_full_schedule_exact_accounting_and_pilot(self):
        plan = self.build()
        self.assertEqual(len(plan['rows']), 475)
        self.assertEqual(plan['rows'][0]['symbols'], list(PILOT))
        for scan in range(79):
            rows = plan['rows'][1+scan*6:7+scan*6]
            self.assertEqual([len(r['symbols']) for r in rows], [100]*5+[17])
            self.assertEqual(sum((r['symbols'] for r in rows), []), self.universe)
        self.assertEqual(self.verify(plan), plan)
        self.assertFalse(plan['execution_authorized'])

    def test_new_date_and_winter_offset(self):
        self.prepare('2026-12-01')
        plan = self.build()
        self.assertEqual(plan['rows'][1]['valid_from'], '2026-12-01T14:30:30+00:00')
        self.assertEqual(plan['finalization_deadline'], '2026-12-01T21:15:00+00:00')

    def test_legacy_schedule_rows_match(self):
        from opportunity_spine_contract import schedule
        self.prepare('2026-09-14')
        old_calendar = dict(calendar='XNYS', session='2026-09-14', open=self.calendar['open'], close=self.calendar['close'])
        old_universe = {'symbols': self.universe}
        old = schedule(old_universe, content_hash(old_universe), old_calendar, content_hash(old_calendar),
                       mode='FULL_OPPORTUNITY_RADAR', root='/')
        new = self.build()
        for i, scan in enumerate(old['scans']):
            for j, members in enumerate(scan['batches']):
                row = new['rows'][1+i*6+j]
                self.assertEqual((row['symbols'], row['valid_from'], row['expires_at']),
                                 (members, scan['start'], scan['end']))

    def test_closed_and_short_sessions_rejected(self):
        for day in ('2026-09-19', '2026-12-25', '2026-11-27'):
            self.prepare(day)
            with self.assertRaisesRegex(ValueError, 'NORMAL_SESSION_REQUIRED'): self.build()

    def test_spine_session_mismatch(self):
        self.spine = exchange_session('2026-09-17').record()
        self.repin()
        with self.assertRaisesRegex(ValueError, 'TRUTH_SPINE_SESSION_MISMATCH'): self.build()

    def test_source_substitution(self):
        with self.assertRaisesRegex(ValueError, 'INTEGRATION_SOURCE'):
            session_plan(self.contract, self.calendar, self.universe, self.spine,
                         expected=self.expected, now=self.now, source_commit='c'*40)

    def test_rehashed_schedule_mutations_rejected(self):
        original = self.build()
        for field, value in (('maximum_requests', 476), ('scope', 'LIVE_EVIDENCE'),
                             ('execution_authorized', True), ('timeout_seconds', 21),
                             ('execution_authorized', 0), ('maximum_requests', 475.0)):
            plan = deepcopy(original); plan[field] = value
            with self.assertRaises(ValueError): self.verify(plan)
        plan = deepcopy(original); plan['rows'][1]['symbols'].reverse()
        with self.assertRaises(ValueError): self.verify(plan)

    def test_missing_or_complete_offline_evidence_never_live(self):
        plan = self.build()
        self.assertEqual(self.join(plan, {}, {})['status'], 'BLOCKED')
        evidence, pins = self.chain(plan)
        result = self.join(plan, evidence, pins)
        self.assertEqual(result['status'], 'OFFLINE_COMPLETE')
        self.assertFalse(result['production_qualified'])
        self.assertFalse(result['execution_authorized'])

    def test_relabel_replay_and_authority_rejected(self):
        plan = self.build()
        for field, value in (('session', '2026-09-14'), ('scope', 'LIVE_EVIDENCE'),
                             ('source_commit', 'c'*40), ('plan_parent', 'd'*64),
                             ('authority', dict.fromkeys(FLAGS, 0))):
            evidence, pins = self.chain(plan)
            evidence[STAGES[0]][field] = value
            pins[STAGES[0]] = content_hash(evidence[STAGES[0]])
            with self.assertRaises(ValueError): self.join(plan, evidence, pins)

    def test_legacy_runner_rejects_candidate_schema(self):
        from alpha_session_runner import validate_package
        plan = self.build()
        with self.assertRaises(ValueError): validate_package(plan, content_hash(plan))

    def test_observation_design_receipt_cannot_enter_full_day_join(self):
        plan=self.build(); evidence,pins=self.chain(plan)
        evidence[STAGES[0]]['schema']='iios-alpha-observation-design-stage-v1'
        pins[STAGES[0]]=content_hash(evidence[STAGES[0]])
        with self.assertRaisesRegex(ValueError,'STAGE_SCHEMA'):self.join(plan,evidence,pins)


if __name__ == '__main__': unittest.main()
