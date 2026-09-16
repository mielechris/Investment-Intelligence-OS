"""Synthetic offline contracts; these inputs are never account/calendar evidence."""
from copy import deepcopy
from datetime import timedelta
import unittest
from unittest.mock import patch

from alpha_short_observation import short_plan, verify_short_plan, OBSERVATION_SCHEMA, PLAN_SCHEMA, PACKAGE_SCHEMA
from alpha_session_package import bound_package, verify_bound_package
from alpha_session_preflight import evaluate_bundle
from provider_gateway_contract import PILOT, content_hash, locked_authority, canonical
import test_alpha_session_integration as integration
import test_alpha_session_package as packages
import test_alpha_session_evidence as evidence


def observation_for(helper):
    from alpha_session_contract import instant
    return dict(schema=OBSERVATION_SCHEMA, session=helper.contract['session'], source_commit='a'*40,
                start=(instant(helper.calendar['open'])+timedelta(minutes=5)).isoformat(),
                symbols=list(PILOT), maximum_requests=3, authority=locked_authority())


class ShortPlanTests(unittest.TestCase):
    def setUp(self):
        self.h=integration.IntegrationTests(); self.h.prepare()
        self.observation=observation_for(self.h)
        self.repin()

    def repin(self):
        self.h.repin(); self.expected={**self.h.expected,'observation':content_hash(self.observation)}

    def build(self):
        h=self.h
        return short_plan(h.contract,h.calendar,h.universe,h.spine,self.observation,
                          expected=self.expected,now=h.now,source_commit='a'*40)

    def verify(self,plan):
        h=self.h
        return verify_short_plan(plan,content_hash(plan),h.contract,h.calendar,h.universe,h.spine,
                                 self.observation,expected=self.expected,now=h.now,source_commit='a'*40)

    def test_exact_pilot_schedule_and_no_authority(self):
        from alpha_session_contract import instant
        plan=self.build(); self.assertEqual(self.verify(plan),plan)
        self.assertEqual(plan['schema'],PLAN_SCHEMA)
        self.assertEqual((plan['maximum_requests'],plan['preflight_requests'],plan['collection_requests']),(3,1,2))
        start=instant(self.observation['start'])
        for slot,row in enumerate(plan['rows']):
            self.assertEqual(row['slot'],slot); self.assertEqual(row['symbols'],list(PILOT))
            self.assertEqual(row['symbol_hash'],content_hash(list(PILOT)))
            self.assertEqual(instant(row['valid_from']),start+timedelta(seconds=slot*60))
            self.assertEqual(instant(row['dispatch_before']),start+timedelta(seconds=slot*60+5))
            self.assertEqual(instant(row['expires_at']),start+timedelta(seconds=slot*60+25))
        self.assertEqual(instant(plan['reconciliation_deadline']),start+timedelta(seconds=180))
        self.assertEqual(instant(plan['finalization_deadline']),start+timedelta(seconds=300))
        self.assertEqual(plan['cleanup_reserve_seconds'],120)
        self.assertEqual(plan['maximum_age_seconds'],60)
        self.assertEqual(plan['route']['parameters'],{'function':'REALTIME_BULK_QUOTES',
            'symbol':','.join(PILOT),'datatype':'json'})
        self.assertFalse(plan['production_qualified']); self.assertFalse(plan['execution_authorized'])
        self.assertTrue(all(v is False for v in plan['authority'].values()))
        for field in ('retry_count','redirect_count','pagination_count','fallback_count','backfill_count','enrichment_requests'):
            self.assertEqual(plan[field],0)

    def test_each_independent_pin_required(self):
        for k in self.expected:
            saved=self.expected[k]; self.expected[k]='f'*64
            with self.subTest(pin=k),self.assertRaises(ValueError):self.build()
            self.expected[k]=saved

    def test_rehashed_window_mutations_rejected(self):
        original=deepcopy(self.observation)
        for k,v in [('schema','other'),('session','2026-09-17'),('source_commit','f'*40),
                    ('maximum_requests',475),('maximum_requests',3.0),('maximum_requests',True),
                    ('symbols',list(reversed(PILOT))),('symbols',list(PILOT[:-1])),
                    ('authority',dict.fromkeys(locked_authority(),0)),('api_key','not-a-real-secret')]:
            self.observation=original|{k:v};self.repin()
            with self.subTest(field=k),self.assertRaises(ValueError):self.build()

    def test_no_closed_historical_or_calendar_substitution(self):
        self.h.prepare('2026-09-19');self.observation=observation_for(self.h);self.repin()
        with self.assertRaisesRegex(ValueError,'SHORT_EXCHANGE_SESSION'):self.build()
        self.h.prepare();self.observation=observation_for(self.h)
        self.h.calendar['close']='2026-09-16T19:00:00+00:00';self.repin()
        with self.assertRaisesRegex(ValueError,'SHORT_CALENDAR_BINDING'):self.build()

    def test_shortened_exchange_day_and_winter_are_explicit(self):
        for day in ('2026-11-27','2026-12-01'):
            self.h.prepare(day);self.observation=observation_for(self.h);self.repin()
            self.assertEqual(self.build()['rows'][0]['valid_from'],day+'T14:35:00+00:00')

    def test_expired_late_preopen_and_cleanup_outside_session(self):
        from alpha_session_contract import instant
        for start in (instant(self.h.calendar['open'])-timedelta(seconds=1),
                      instant(self.h.calendar['close'])-timedelta(seconds=299)):
            self.observation['start']=start.isoformat();self.repin()
            with self.assertRaisesRegex(ValueError,'SHORT_WINDOW'):self.build()
        self.observation=observation_for(self.h);self.repin()
        self.h.now=instant(self.observation['start'])
        with self.assertRaisesRegex(ValueError,'SHORT_WINDOW'):self.build()

    def test_rehashed_plan_cannot_change_any_boundary(self):
        original=self.build()
        for k,v in [('maximum_requests',475),('scope','LIVE_QUALIFICATION'),('timeout_seconds',21),
                    ('maximum_response_bytes',1000001),('maximum_age_seconds',61),('cleanup_reserve_seconds',0),
                    ('authority',dict.fromkeys(locked_authority(),True)),('retry_count',1),
                    ('production_qualified',True),('execution_authorized',0),('stop_on',[]),
                    ('lifecycle_requirements',[]),('finalization_deadline',self.h.contract['expires_at']),
                    ('coverage','FULL_UNIVERSE'),('evidence_policy','RETAIN_RAW')]:
            value=deepcopy(original);value[k]=v
            with self.subTest(field=k),self.assertRaises(ValueError):self.verify(value)
        for rows in (original['rows'][1:],original['rows']+original['rows'][:1],list(reversed(original['rows']))):
            with self.assertRaises(ValueError):self.verify(original|{'rows':rows})
        value=deepcopy(original);value['rows'][1]['symbols']=self.h.universe[:10]
        with self.assertRaises(ValueError):self.verify(value)

    def test_full_day_count_does_not_select_short_contract(self):
        plan=self.h.build();plan['maximum_requests']=3
        from alpha_session_integration import verify_session_plan
        with self.assertRaises(ValueError):
            verify_session_plan(plan,content_hash(plan),self.h.contract,self.h.calendar,self.h.universe,
                                self.h.spine,**self.h.args())
        with self.assertRaisesRegex(ValueError,'FULL_SESSION_OBSERVATION_FORBIDDEN'):
            verify_session_plan(self.h.build(),content_hash(self.h.build()),self.h.contract,self.h.calendar,
                                self.h.universe,self.h.spine,observation=self.observation,**self.h.args())

    def test_plan_never_performs_io(self):
        with patch('subprocess.run',side_effect=AssertionError('NO_PROCESS')),\
             patch('socket.socket',side_effect=AssertionError('NO_NETWORK')),\
             patch('builtins.open',side_effect=AssertionError('NO_FILES')):
            self.build()


def adapt_package(f):
    h=f.helper;obs=observation_for(h)
    h.expected['observation']=content_hash(obs)
    f.plan=short_plan(h.contract,h.calendar,h.universe,h.spine,obs,**h.args())
    for name in ('account','runtime','allowance'):getattr(f,name)['plan_parent']=content_hash(f.plan)
    f.account.update(symbols=list(PILOT),available_unreserved='3')
    f.allowance.update(maximum_requests=3,maximum_cost='3')
    f.repin()
    return obs


class ShortPackageTests(unittest.TestCase):
    def setUp(self):
        self.f=packages.PackageTests();self.f.setUp();self.obs=adapt_package(self.f)

    def build(self):
        f=self.f
        return bound_package(f.plan,f.account,f.runtime,f.allowance,observation=self.obs,**f.kwargs())

    def test_exact_cost_never_releases_or_qualifies(self):
        result=self.build();self.assertEqual(result['schema'],PACKAGE_SCHEMA)
        self.assertEqual(result['maximum_requests'],3);self.assertEqual(result['maximum_cost'],'3')
        self.assertFalse(result['allowance_released']);self.assertFalse(result['execution_authorized'])
        from alpha_session_runner import validate_package
        with self.assertRaises(ValueError):validate_package(result,content_hash(result))

    def test_cost_from_evidence_decimal_exactness(self):
        self.f.account.update(maximum_request_cost='0.00000001',available_unreserved='0.00000003')
        self.f.allowance['maximum_cost']='0.00000003';self.f.repin()
        from decimal import localcontext
        with localcontext() as c:
            c.prec=2;self.assertEqual(self.build()['maximum_cost'],'0.00000003')

    def test_invalid_allowance_or_account_claims_fail(self):
        for field,value in [('maximum_requests',475),('maximum_requests',3.0),('maximum_cost','2'),
                            ('released',True),('enrichment_requests',1)]:
            old=deepcopy(self.f.allowance);self.f.allowance[field]=value;self.f.repin()
            with self.subTest(field=field),self.assertRaises(ValueError):self.build()
            self.f.allowance=old;self.f.repin()
        self.f.account['claim_parents']={};self.f.repin()
        with self.assertRaises(ValueError):self.build()

    def test_full_package_relabel_and_rehashed_source_rejected(self):
        f=self.f;result=self.build()
        for field,value in [('schema','iios-alpha-bound-package-candidate-v1'),('source_commit','f'*40),
                            ('production_qualified',True),('maximum_requests',475)]:
            candidate=result|{field:value}
            with self.assertRaises(ValueError):
                verify_bound_package(candidate,content_hash(candidate),f.plan,f.account,f.runtime,f.allowance,
                                     observation=self.obs,**f.kwargs())


class ShortReadOnlyEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.e=evidence.CandidateEvidenceTests();self.e.setUp();f=self.e.fixture
        self.obs=adapt_package(f)
        for claim,name in self.e.claims_manifest['claims'].items():
            p=self.e.claims_root/name;doc=evidence.json_document(p.read_bytes())
            doc['symbols_parent']=content_hash(list(PILOT));p.chmod(0o600)
            self.e.claims_root.chmod(0o700)
            row=evidence.write(self.e.claims_root,name,canonical(doc));self.e.claims_root.chmod(0o500)
            self.e.claims_manifest['files']=[row if x['path']==name else x for x in self.e.claims_manifest['files']]
            f.account['claim_parents'][claim]=content_hash(doc)
        f.repin();self.e.claims_manifest['account_parent']=f.pins['account']
        candidate=bound_package(f.plan,f.account,f.runtime,f.allowance,observation=self.obs,**f.kwargs())
        inputs=f.kwargs();self.now=inputs.pop('now');inputs['observation']=self.obs
        self.bundle=dict(schema='iios-alpha-short-preflight-input-v1',candidate=candidate,
                         candidate_hash=content_hash(candidate),plan=f.plan,account=f.account,runtime=f.runtime,
                         allowance=f.allowance,runtime_manifest=self.e.runtime_manifest,
                         claims_manifest=self.e.claims_manifest,claims_manifest_hash=content_hash(self.e.claims_manifest),
                         package_inputs=inputs)

    def tearDown(self):self.e.tearDown()

    def check(self):
        return evaluate_bundle(self.bundle,now=self.now,approved_runtime_root=str(self.e.runtime_root),
                               approved_claims_root=str(self.e.claims_root))

    def test_short_file_evidence_stays_blocked(self):
        with patch('subprocess.run',side_effect=AssertionError('NO_PROCESS')):
            result=self.check()
        self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(result['candidate_evidence'],'FILES_AND_BINDINGS_VERIFIED_ONLY')
        self.assertEqual(result['provider_requests'],0);self.assertEqual(result['process_launches'],0)
        self.assertFalse(result['production_qualified']);self.assertFalse(result['execution_authorized'])

    def test_cross_mode_bundle_and_missing_window_rejected(self):
        self.bundle['schema']='iios-alpha-preflight-input-v1'
        with self.assertRaisesRegex(ValueError,'PREFLIGHT_MODE_BINDING'):self.check()
        self.bundle['schema']='iios-alpha-short-preflight-input-v1';del self.bundle['package_inputs']['observation']
        with self.assertRaisesRegex(ValueError,'PREFLIGHT_INPUT_SCHEMA'):self.check()

    def test_old_runtime_source_and_claim_hash_rejected(self):
        self.bundle['runtime_manifest']['release_commit']='f'*40
        with self.assertRaises(ValueError):self.check()
        self.bundle['runtime_manifest']['release_commit']='a'*40
        self.bundle['claims_manifest_hash']='f'*64
        with self.assertRaises(ValueError):self.check()

    def test_serialized_cli_path_still_requires_all_independent_pins(self):
        from alpha_session_preflight import main
        from datetime import datetime
        from contextlib import redirect_stdout
        import io,json
        root=self.e.base/'input';root.mkdir()
        row=evidence.write(root,'admission-input.json',canonical(self.bundle));root.chmod(0o500)
        args=['--input-root',str(root),'--expected-sha256',row['sha256'],'--expected-bytes',str(row['size']),
              '--approved-runtime-root',str(self.e.runtime_root),'--approved-claims-root',str(self.e.claims_root)]
        stamp=self.now
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return stamp
        stream=io.StringIO()
        with patch('alpha_session_preflight.datetime',Clock),redirect_stdout(stream),\
             patch('subprocess.run',side_effect=AssertionError('NO_PROCESS')):
            self.assertEqual(main(args),2)
        result=json.loads(stream.getvalue())
        self.assertEqual(result['candidate_evidence'],'FILES_AND_BINDINGS_VERIFIED_ONLY')
        self.assertEqual(result['status'],'BLOCKED');self.assertFalse(result['execution_authorized'])
        args[3]='f'*64
        with redirect_stdout(io.StringIO()):self.assertEqual(main(args),1)


if __name__=='__main__':unittest.main()
