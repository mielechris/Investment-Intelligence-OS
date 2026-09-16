"""No account facts or payment model are inferred by these synthetic tests."""
from copy import deepcopy
from decimal import localcontext
import unittest

import test_alpha_short_observation as fixtures
from alpha_observation_billing import review_billing, SCHEMA
from provider_gateway_contract import content_hash, locked_authority


class BillingTests(unittest.TestCase):
    def setUp(self):
        h=fixtures.ShortPackageTests();h.setUp();self.f=h.f
        self.plan=h.f.plan;self.parents={k:content_hash(k) for k in ('cost','billing','rate')}
        self.doc=dict(schema=SCHEMA,scope='OFFLINE_INTEGRATION_ONLY',source_commit='a'*40,
            plan_parent=content_hash(self.plan),account_identity='synthetic-account',
            valid_from=self.f.account['valid_from'],expires_at=self.f.account['expires_at'],
            model='METERED_CURRENCY',evidence_parents=self.parents,currency='USD',
            maximum_request_charge='0.02',spending_cap='0.06',spending_headroom='0.10',
            request_cap=3,available_requests=3,quota_unlimited=False,unit_name=None,
            units_per_request=None,available_units=None,overage_enabled=False,automatic_top_up=False,
            ambiguous_policy='RESERVE_MAXIMUM_NO_RETRY',zero_incremental_charge_proven=False,
            authority=locked_authority())

    def build(self):
        return review_billing(self.doc,content_hash(self.doc),plan=self.plan,plan_hash=content_hash(self.plan),
            account_identity='synthetic-account',evidence_parents=self.parents,now=self.f.helper.now)

    def test_metered_explicit_request_and_spending_caps(self):
        r=self.build();self.assertEqual(r['maximum_spend'],'0.06');self.assertEqual(r['request_cap'],3)
        self.assertIsNone(r['prepaid_units_reserved_maximum']);self.assertFalse(r['allowance_released'])
        self.assertEqual(r['package_projection']['available_unreserved'],'0.10')

    def test_flat_subscription_does_not_assume_zero(self):
        self.doc.update(model='FLAT_SUBSCRIPTION',quota_unlimited=True,available_requests=None)
        self.assertEqual(self.build()['maximum_spend'],'0.06')
        self.doc['maximum_request_charge']='0'
        with self.assertRaisesRegex(ValueError,'ZERO_UNPROVEN'):self.build()
        self.doc['zero_incremental_charge_proven']=True
        self.assertEqual(self.build()['maximum_spend'],'0');self.assertEqual(self.build()['request_cap'],3)

    def test_prepaid_balance_separate_from_currency(self):
        self.doc.update(model='PREPAID_UNITS',unit_name='request-unit',units_per_request='2',available_units='6')
        self.assertEqual(self.build()['prepaid_units_reserved_maximum'],'6')
        self.doc['available_units']='5.999'
        with self.assertRaisesRegex(ValueError,'PREPAID_HEADROOM'):self.build()

    def test_nonprepaid_rejects_fabricated_credit_balance(self):
        self.doc['available_units']='100'
        with self.assertRaisesRegex(ValueError,'NOT_PREPAID'):self.build()

    def test_every_cap_and_billing_safety_mutation(self):
        original=deepcopy(self.doc)
        for field,value in [('model','UNKNOWN'),('request_cap',True),('request_cap',4),('spending_cap','0.05'),
            ('spending_headroom','0.01'),('available_requests',2),('quota_unlimited',True),
            ('overage_enabled',True),('automatic_top_up',0),('ambiguous_policy','RELEASE_ON_TIMEOUT'),
            ('currency','credits'),('maximum_request_charge','NaN'),('maximum_request_charge','-1'),
            ('maximum_request_charge','1e2'),('maximum_request_charge',False),('spending_cap','9'*100)]:
            self.doc=original|{field:value}
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.build()

    def test_source_account_parent_validity_and_authority(self):
        original=deepcopy(self.doc)
        for field,value in [('scope','LIVE'),('source_commit','e'*40),('account_identity','other'),
            ('plan_parent','f'*64),('evidence_parents',{}),('expires_at',self.doc['valid_from']),
            ('authority',dict.fromkeys(locked_authority(),True))]:
            self.doc=original|{field:value}
            with self.subTest(field=field),self.assertRaises(ValueError):self.build()

    def test_independent_hash_and_public_pricing_not_enough(self):
        with self.assertRaises(ValueError):review_billing(self.doc,'f'*64,plan=self.plan,plan_hash=content_hash(self.plan),account_identity='synthetic-account',evidence_parents=self.parents,now=self.f.helper.now)
        self.doc['evidence_parents']={'public_pricing':'a'*64}
        with self.assertRaises(ValueError):self.build()

    def test_decimal_context_exact_and_large_finite_values(self):
        self.doc.update(maximum_request_charge='0.00000001',spending_cap='0.00000003',spending_headroom='1')
        with localcontext() as ctx:
            ctx.prec=2;self.assertEqual(self.build()['maximum_spend'],'0.00000003')

    def test_existing_package_accepts_currency_without_prepaid_inference(self):
        h=fixtures.ShortPackageTests();h.setUp();projection=self.build()['package_projection']
        h.f.account.update({k:v for k,v in projection.items() if k!='maximum_cost'})
        h.f.allowance.update(cost_unit='USD',maximum_cost=projection['maximum_cost'])
        h.f.repin();self.assertEqual(h.build()['maximum_cost'],'0.06')


if __name__=='__main__':unittest.main()
