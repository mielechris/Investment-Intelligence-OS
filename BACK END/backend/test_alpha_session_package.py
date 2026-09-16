"""In-memory synthetic references, never real accounts or runtime acceptance."""
from copy import deepcopy
import unittest

from alpha_session_package import bound_package, verify_bound_package
from alpha_session_integration import SCOPE
from provider_gateway_contract import content_hash
from provider_gateway_live_contract import CLAIMS
import test_alpha_session_integration as fixtures


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.helper = fixtures.IntegrationTests()
        self.helper.prepare()
        self.plan = self.helper.build()
        common = dict(scope=SCOPE, source_commit='a'*40, session=self.plan['session'],
                      plan_parent=content_hash(self.plan), valid_from=self.helper.contract['valid_from'],
                      expires_at=self.helper.contract['expires_at'])
        self.account = dict(common, schema='iios-alpha-account-candidate-v1', account_identity='synthetic-account',
                            tier_identity='synthetic-tier', provider='ALPHA_VANTAGE', endpoint='REALTIME_BULK_QUOTES',
                            feed='real_time', symbols=list(dict.fromkeys(s for r in self.plan['rows'] for s in r['symbols'])),
                            claim_parents={key:'b'*64 for key in CLAIMS}, cost_unit='synthetic-unit',
                            maximum_request_cost='1', available_unreserved='475', rate_per_minute=3,
                            overage_enabled=False, automatic_top_up=False, ambiguous_billing='RESERVE_MAXIMUM_NO_RETRY')
        self.runtime = dict(common, schema='iios-alpha-runtime-candidate-v1', runtime_manifest_sha256='c'*64,
                            interpreter_sha256='d'*64, platform_manifest_sha256='e'*64,
                            python_version='3.14.7', system='Darwin', architecture='arm64')
        self.allowance = dict(common, schema='iios-alpha-allowance-candidate-v1', account_parent='', runtime_parent='',
                              account_identity='synthetic-account', cost_unit='synthetic-unit', maximum_requests=475,
                              maximum_cost='475', enrichment_requests=0, released=False)
        self.repin()

    def repin(self):
        self.allowance.update(account_parent=content_hash(self.account), runtime_parent=content_hash(self.runtime))
        self.pins = {key:content_hash(getattr(self,key)) for key in ('plan','account','runtime','allowance')}

    def kwargs(self):
        h = self.helper
        return dict(input_pins=self.pins, contract=h.contract, calendar=h.calendar, universe=h.universe,
                    spine_session=h.spine, expected=h.expected, now=h.now, source_commit='a'*40)

    def build(self): return bound_package(self.plan,self.account,self.runtime,self.allowance,**self.kwargs())

    def test_complete_binding_never_releases_authority(self):
        result = self.build()
        self.assertEqual(result['status'], 'BINDINGS_VALID_ONLY')
        self.assertTrue(all(v is False for v in result['authority'].values()))
        for field in ('qualification_authorized','execution_authorized','production_qualified','allowance_released'):
            self.assertIs(result[field], False)
        self.assertIn('REAL_ACCOUNT_EVIDENCE', result['pending'])

    def test_independent_hashes_required(self):
        for key in self.pins:
            old = self.pins[key]; self.pins[key]='f'*64
            with self.subTest(key=key), self.assertRaises(ValueError): self.build()
            self.pins[key]=old

    def test_scope_session_source_and_window_mutations(self):
        for name in ('account','runtime','allowance'):
            original = deepcopy(getattr(self,name))
            for field,value in (('scope','LIVE_QUALIFICATION'),('session','2026-09-14'),('source_commit','f'*40),
                                ('plan_parent','f'*64),('expires_at',self.helper.now.isoformat())):
                setattr(self,name,original|{field:value}); self.repin()
                with self.subTest(name=name,field=field), self.assertRaises(ValueError): self.build()
            setattr(self,name,original); self.repin()

    def test_account_and_runtime_substitutions(self):
        for name, mutations in (
            ('account', [('provider','MASSIVE'),('feed','delayed'),('symbols',self.helper.universe),
                         ('claim_parents',{}),('rate_per_minute',True),('rate_per_minute',2),
                         ('overage_enabled',True),('automatic_top_up',0)]),
            ('runtime', [('python_version','3.13.15'),('system','Linux'),('architecture','x86_64'),
                         ('runtime_manifest_sha256',''),('interpreter_sha256','unbound')])):
            original=deepcopy(getattr(self,name))
            for field,value in mutations:
                setattr(self,name,original|{field:value}); self.repin()
                with self.subTest(name=name,field=field), self.assertRaises(ValueError): self.build()
            setattr(self,name,original); self.repin()

    def test_allowance_parent_and_budget_mutations(self):
        original=deepcopy(self.allowance)
        for field,value in [('account_parent','f'*64),('runtime_parent','f'*64),('account_identity','other'),
                            ('maximum_requests',475.0),('maximum_requests',476),('maximum_cost','474'),
                            ('enrichment_requests',False),('enrichment_requests',1),('released',True),
                            ('cost_unit','other')]:
            self.allowance=original|{field:value}
            self.pins['allowance']=content_hash(self.allowance)
            with self.subTest(field=field), self.assertRaises(ValueError): self.build()

    def test_insufficient_available_and_invalid_money(self):
        self.account['available_unreserved']='474.99'; self.repin()
        with self.assertRaises(ValueError): self.build()
        for value in ('NaN','Infinity','-1','1e3',1,True,'9'*100):
            self.account['maximum_request_cost']=value; self.repin()
            with self.subTest(value=value), self.assertRaises(ValueError): self.build()

    def test_small_exact_cost_and_decimal_context(self):
        from decimal import localcontext
        self.account.update(maximum_request_cost='0.00000001',available_unreserved='0.00000475')
        self.allowance['maximum_cost']='0.00000475'; self.repin()
        with localcontext() as ctx:
            ctx.prec=2
            self.assertEqual(self.build()['maximum_cost'],'0.00000475')

    def test_extra_credential_field_rejected(self):
        self.account['api_key']='synthetic-not-a-credential'; self.repin()
        with self.assertRaises(ValueError): self.build()

    def test_rehashed_output_authority_mutation_rejected(self):
        result=self.build(); result['execution_authorized']=0
        with self.assertRaises(ValueError):
            verify_bound_package(result,content_hash(result),self.plan,self.account,self.runtime,self.allowance,**self.kwargs())

    def test_old_runner_cannot_execute_bound_candidate(self):
        from alpha_session_runner import validate_package
        result=self.build()
        with self.assertRaises(ValueError): validate_package(result,content_hash(result))


if __name__ == '__main__': unittest.main()
