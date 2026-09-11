"""Synthetic qualification fixtures shared only by the new offline tests."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from provider_gateway_contract import content_hash, locked_authority, PROVIDER_ROLES
from provider_gateway_live_contract import admit, CLAIMS, ROUTES, SELECTORS, request_parameters

NOW = '2026-09-14T13:30:30+00:00'
END = '2026-09-14T20:05:00+00:00'


def fixture(provider='ALPACA'):
    base = Path(os.environ['IIOS_GATEWAY_TEST_ROOT'])
    if not base.is_absolute() or base.resolve() != base or not base.name.startswith('iios-provider-connection-source-tests-'):
        raise ValueError('EXACT_SYNTHETIC_ROOT_REQUIRED')
    root = Path(tempfile.mkdtemp(prefix='case-', dir=base))
    output = root / 'output'
    output.mkdir(mode=0o700)
    runtime_root = root / 'runtime'
    runtime_root.mkdir(mode=0o700)
    rows = []
    for name, body, mode in (('python', b'synthetic interpreter only', 0o500), ('tls.pem', b'synthetic TLS input only', 0o400), ('source.py', b'# synthetic source\n', 0o400)):
        p = runtime_root / name
        p.write_bytes(body)
        p.chmod(mode)
        rows.append({'path': name, 'sha256': hashlib.sha256(body).hexdigest(), 'size': len(body), 'mode': mode})
    runtime_root.chmod(0o500)
    runtime = {'scope': 'OFFLINE_TEST', 'source_commit': '1' * 40, 'root': str(runtime_root), 'files': rows, 'interpreter': 'python', 'tls': 'tls.pem', 'source_files': ['source.py'], 'network_addresses': {p: '192.0.2.1' for p in ROUTES}}
    method, host, path, endpoint = ROUTES[provider]
    feed = {'ALPACA': 'iex', 'MASSIVE': 'real_time', 'FINANCIAL_DATASETS': 'corporate_historical', 'BIGDATA': 'research', 'ALPHA_VANTAGE': 'enrichment'}[provider]
    account = {'provider': provider, 'scope': 'OFFLINE_TEST', 'account_identity': 'synthetic-account', 'tier_identity': 'synthetic-tier', 'selectors': [{'service': s, 'account': 'iios-provider'} for s in SELECTORS[provider]], 'endpoint': endpoint, 'feed': feed, 'symbols': ['MU'], 'valid_from': '2026-09-14T00:00:00+00:00', 'expires_at': END, 'proofs': {c: {'status': 'VERIFIED', 'evidence_sha256': 'a' * 64} for c in CLAIMS}, 'cost_unit': 'synthetic-unit', 'maximum_request_cost': '1', 'available_unreserved': '1', 'rate_per_minute': 1, 'rate_slot_reserved': True, 'overage_enabled': False, 'automatic_top_up': False, 'ambiguous_billing': 'RESERVE_MAXIMUM_NO_RETRY', 'retention': {'raw_body': True, 'normalized': True, 'references': True, 'hashes': True, 'agreement_sha256': 'a' * 64, 'retain_until': END, 'explicit_api_storage_permission': True, 'no_grounding_or_model_call': True}}
    manifest = {'schema': 'iios-provider-qualification-v1', 'mode': 'OFFLINE_TEST', 'batch_id': 'synthetic-batch', 'provider': provider, 'role': PROVIDER_ROLES[provider], 'source_commit': runtime['source_commit'], 'account_parent': content_hash(account), 'runtime_parent': content_hash(runtime), 'root': str(output), 'symbols': ['MU'], 'feed': feed, 'method': method, 'host': host, 'path': path, 'endpoint': endpoint, 'parameters': request_parameters(provider, ['MU'], feed), 'valid_from': NOW, 'expires_at': END, 'maximum_requests': 1, 'maximum_cost': '1', 'cost_unit': 'synthetic-unit', 'timeout_seconds': 5, 'maximum_response_bytes': 100000, 'maximum_age_seconds': 60, 'authority': locked_authority(), 'qualification_authorized': True}
    return manifest, account, runtime


def pins(m, a, r):
    return {'manifest': content_hash(m), 'account': content_hash(a), 'runtime': content_hash(r)}


def repin(m, a, r):
    m['account_parent'], m['runtime_parent'] = content_hash(a), content_hash(r)
    return pins(m, a, r)


def admitted(provider='ALPACA'):
    m, a, r = fixture(provider)
    return admit(m, a, r, expected=pins(m, a, r), now=NOW)


class ContractTests(unittest.TestCase):
    def test_all_five_explicit_roles_admit_synthetic_only(self):
        for provider in ROUTES:
            with self.subTest(provider=provider):
                admission = admitted(provider)
                self.assertEqual(admission.documents()[0]['mode'], 'OFFLINE_TEST')

    def test_each_account_proof_required(self):
        for claim in CLAIMS:
            m, a, r = fixture()
            del a['proofs'][claim]
            with self.subTest(claim=claim), self.assertRaises(ValueError):
                admit(m, a, r, expected=repin(m, a, r), now=NOW)

    def test_unknown_proof_not_account_evidence(self):
        m, a, r = fixture()
        a['proofs']['endpoint']['status'] = 'CHATGPT_CONNECTED'
        with self.assertRaises(ValueError):
            admit(m, a, r, expected=repin(m, a, r), now=NOW)

    def test_all_operational_flags_stay_false(self):
        for flag in locked_authority():
            m, a, r = fixture()
            m['authority'][flag] = True
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                admit(m, a, r, expected=pins(m, a, r), now=NOW)

    def test_wrong_self_parent_and_missing_independent_pin(self):
        m, a, r = fixture()
        for expected in ({}, {**pins(m, a, r), 'account': '0' * 64}):
            with self.assertRaises(ValueError):
                admit(m, a, r, expected=expected, now=NOW)
        m['account_parent'] = '0' * 64
        with self.assertRaises(ValueError):
            admit(m, a, r, expected=pins(m, a, r), now=NOW)

    def test_mutation_does_not_change_admitted_bytes(self):
        m, a, r = fixture()
        admission = admit(m, a, r, expected=pins(m, a, r), now=NOW)
        m['host'] = 'wrong.invalid'
        a['selectors'] = []
        self.assertEqual(admission.recheck(NOW).documents()[0]['host'], ROUTES['ALPACA'][1])

    def test_legacy_and_alternate_selectors_rejected(self):
        for service in ('com.iios.expansion-wing.financial-datasets', 'IIOS_OTHER_API_KEY'):
            m, a, r = fixture('FINANCIAL_DATASETS')
            a['selectors'][0]['service'] = service
            with self.assertRaises(ValueError):
                admit(m, a, r, expected=repin(m, a, r), now=NOW)

    def test_paper_does_not_imply_sip(self):
        m, a, r = fixture()
        m['feed'] = 'sip'
        m['parameters']['feed'] = 'sip'
        with self.assertRaises(ValueError):
            admit(m, a, r, expected=pins(m, a, r), now=NOW)

    def test_bigdata_every_storage_class_requires_explicit_permission(self):
        for field in ('raw_body', 'normalized', 'references', 'hashes', 'explicit_api_storage_permission', 'no_grounding_or_model_call'):
            m, a, r = fixture('BIGDATA')
            a['retention'][field] = False
            with self.subTest(field=field), self.assertRaises(ValueError):
                admit(m, a, r, expected=repin(m, a, r), now=NOW)

    def test_expiry_budget_route_and_scope(self):
        changes = ({'maximum_requests': 2}, {'maximum_cost': '2'}, {'expires_at': NOW}, {'path': '/v2/orders'}, {'host': 'paper-api.alpaca.markets'}, {'mode': 'LIVE_QUALIFICATION'}, {'symbols': []}, {'qualification_authorized': False}, {'parameters': {}}, {'role': 'EXECUTION'})
        for patch in changes:
            m, a, r = fixture()
            m.update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                admit(m, a, r, expected=pins(m, a, r), now=NOW)

    def test_cost_and_rate_missing_never_guessed(self):
        for patch in ({'available_unreserved': '0'}, {'maximum_request_cost': '2'}, {'rate_slot_reserved': False}, {'overage_enabled': True}, {'automatic_top_up': True}, {'ambiguous_billing': 'UNKNOWN'}, {'rate_per_minute': 0}):
            m, a, r = fixture()
            a.update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                admit(m, a, r, expected=repin(m, a, r), now=NOW)

    def test_live_cannot_claim_accepted_offline_base(self):
        from provider_gateway_live_contract import BASE
        m, a, r = fixture()
        m['mode'] = a['scope'] = r['scope'] = 'LIVE_QUALIFICATION'
        m['source_commit'] = r['source_commit'] = BASE
        with self.assertRaises(ValueError):
            admit(m, a, r, expected=repin(m, a, r), now=NOW)
