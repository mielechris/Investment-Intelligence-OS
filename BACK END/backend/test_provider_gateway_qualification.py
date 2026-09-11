import ast
import hashlib
import json
import os
from pathlib import Path
import unittest

from provider_gateway_live_contract import admit
from provider_gateway_qualification import qualify, verify_runtime
from test_provider_gateway_live_contract import fixture, pins, repin, NOW
from test_provider_gateway_credentials import FakeCredentials, FAKE
from test_provider_gateway_transport import FakeNetwork
from test_provider_gateway_wire import facts, research, enrichment


class QualificationTests(unittest.TestCase):
    def run_case(self, provider='ALPACA', network=None):
        m, a, r = fixture(provider)
        fake = network or FakeNetwork()
        receipt = qualify(m, a, r, expected=pins(m, a, r), credential_backend=FakeCredentials(), network=fake, clock=lambda: NOW)
        return m, a, r, fake, receipt

    def test_normal_five_provider_mocked_receipts_only(self):
        payloads = {'ALPACA': None, 'MASSIVE': {'tickers': [{'ticker': 'MU'}]}, 'FINANCIAL_DATASETS': facts(), 'BIGDATA': research(), 'ALPHA_VANTAGE': enrichment()}
        for provider, payload in payloads.items():
            m, a, r, network, receipt = self.run_case(provider, FakeNetwork(payload=payload))
            self.assertEqual(network.calls, 1)
            self.assertEqual(receipt['result'], 'OBSERVED')
            self.assertEqual(receipt['scope'], 'OFFLINE_TEST')
            self.assertEqual(receipt['provider_readiness'], 'NOT_READY')
            self.assertEqual(receipt['billing'], 'UNVERIFIED')
            self.assertTrue(all(v is False for v in receipt['authority'].values()))
            path = Path(m['root']) / (provider + '.receipt.json')
            self.assertEqual(json.loads(path.read_text()), receipt)
            self.assertEqual(receipt['parents']['manifest'], pins(m, a, r)['manifest'])
            body = json.loads((Path(m['root']) / (provider + '.response.json')).read_text())['raw_utf8'].encode()
            self.assertEqual(hashlib.sha256(body).hexdigest(), receipt['raw_response_sha256'])

    def test_duplicate_cannot_dispatch_or_overwrite(self):
        m, a, r, fake, _ = self.run_case()
        target = Path(m['root']) / 'ALPACA.receipt.json'
        before = target.read_bytes()
        with self.assertRaises(ValueError):
            qualify(m, a, r, expected=pins(m, a, r), credential_backend=FakeCredentials(), network=fake, clock=lambda: NOW)
        self.assertEqual(fake.calls, 1)
        self.assertEqual(target.read_bytes(), before)
        self.assertTrue(list(Path(m['root']).glob('failure-*.json')))

    def test_ambiguous_attempt_blocks_rest_of_batch(self):
        m, a, r, fake, receipt = self.run_case(network=FakeNetwork(failure=True))
        self.assertEqual(receipt['result'], 'AMBIGUOUS_OR_UNVERIFIED_STOP')
        self.assertEqual(receipt['billing'], 'AMBIGUOUS_MAXIMUM_RETAINED')
        self.assertTrue((Path(m['root']) / 'STOP.json').exists())
        with self.assertRaises(ValueError):
            qualify(m, a, r, expected=pins(m, a, r), credential_backend=FakeCredentials(), network=fake, clock=lambda: NOW)
        self.assertEqual(fake.calls, 1)

    def test_credential_exception_no_dispatch_no_secret_persistence(self):
        m, a, r = fixture()
        fake = FakeNetwork()
        receipt = qualify(m, a, r, expected=pins(m, a, r), credential_backend=FakeCredentials(1), network=fake, clock=lambda: NOW)
        self.assertEqual(fake.calls, 0)
        self.assertEqual(receipt['result'], 'AMBIGUOUS_OR_UNVERIFIED_STOP')
        for path in Path(m['root']).iterdir():
            self.assertNotIn(FAKE, path.read_bytes())

    def test_secret_echo_never_hashed_or_persisted(self):
        m, _, _, _, receipt = self.run_case(network=FakeNetwork(payload={'name': FAKE.decode()}))
        self.assertIsNone(receipt['raw_response_sha256'])
        self.assertIsNone(receipt['normalized_sha256'])
        for path in Path(m['root']).iterdir():
            self.assertNotIn(FAKE, path.read_bytes())

    def test_missing_account_blocks_before_credentials_network_and_writes(self):
        m, a, r = fixture()
        a['proofs'] = {}
        fake, credentials = FakeNetwork(), FakeCredentials()
        with self.assertRaises(ValueError):
            qualify(m, a, r, expected=repin(m, a, r), credential_backend=credentials, network=fake, clock=lambda: NOW)
        self.assertEqual(fake.calls, 0)
        self.assertEqual(credentials.calls, [])
        self.assertEqual(list(Path(m['root']).iterdir()), [])

    def test_bigdata_unknown_reference_retention_blocks_all_storage(self):
        m, a, r = fixture('BIGDATA')
        a['retention']['references'] = None
        fake = FakeNetwork(payload=research())
        with self.assertRaises(ValueError):
            qualify(m, a, r, expected=repin(m, a, r), credential_backend=FakeCredentials(), network=fake, clock=lambda: NOW)
        self.assertEqual(fake.calls, 0)
        self.assertEqual(list(Path(m['root']).iterdir()), [])

    def test_runtime_tamper_missing_extra_and_modes(self):
        for kind in ('hash', 'missing', 'extra', 'mode', 'source', 'interpreter'):
            m, a, r = fixture()
            if kind == 'hash':
                r['files'][0]['sha256'] = '0' * 64
            elif kind == 'missing':
                r['files'].pop()
            elif kind == 'extra':
                r['files'].append({**r['files'][0], 'path': 'not-present'})
            elif kind == 'mode':
                (Path(r['root']) / 'tls.pem').chmod(0o660)
            elif kind == 'source':
                r['source_files'] = ['not-present']
            else:
                r['interpreter'] = 'tls.pem'
            with self.subTest(kind=kind), self.assertRaises((ValueError, OSError)):
                verify_runtime(admit(m, a, r, expected=repin(m, a, r), now=NOW))

    def test_runtime_symlink_and_hardlink_substitution(self):
        for kind in ('symlink', 'hardlink'):
            m, a, r = fixture()
            root = Path(r['root'])
            root.chmod(0o700)
            if kind == 'symlink':
                (root / 'alias').symlink_to(root / 'python')
            else:
                os.link(root / 'python', root / 'alias')
            root.chmod(0o500)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                verify_runtime(admit(m, a, r, expected=repin(m, a, r), now=NOW))

    def test_runtime_relocation_with_old_pin_rejected(self):
        m, a, r = fixture()
        expected = pins(m, a, r)
        r['root'] = str(Path(r['root']).parent)
        with self.assertRaises(ValueError):
            admit(m, a, r, expected=expected, now=NOW)

    def test_output_symlink_and_preexisting_receipt_fail_closed(self):
        m, a, r = fixture()
        output = Path(m['root'])
        (output / 'ALPACA.reserved.json').write_text('preserved synthetic collision')
        fake = FakeNetwork()
        with self.assertRaises(ValueError):
            qualify(m, a, r, expected=pins(m, a, r), credential_backend=FakeCredentials(), network=fake, clock=lambda: NOW)
        self.assertEqual(fake.calls, 0)
        self.assertEqual((output / 'ALPACA.reserved.json').read_text(), 'preserved synthetic collision')
        m, a, r = fixture()
        output = Path(m['root'])
        (output / 'batch.lock').symlink_to(output / 'elsewhere')
        with self.assertRaises(ValueError):
            qualify(m, a, r, expected=pins(m, a, r), credential_backend=FakeCredentials(), network=fake, clock=lambda: NOW)
        self.assertEqual(fake.calls, 0)
        self.assertFalse((output / 'elsewhere').exists())

    def test_mock_boundaries_cannot_produce_live_receipt(self):
        m, a, r = fixture()
        m['mode'] = a['scope'] = r['scope'] = 'LIVE_QUALIFICATION'
        with self.assertRaises(ValueError):
            qualify(m, a, r, expected=repin(m, a, r), credential_backend=FakeCredentials(), network=FakeNetwork())

    def test_runtime_wrong_actual_interpreter_rejected(self):
        m, a, r = fixture()
        m['mode'] = a['scope'] = r['scope'] = 'LIVE_QUALIFICATION'
        with self.assertRaisesRegex(ValueError, 'INTERPRETER'):
            verify_runtime(admit(m, a, r, expected=repin(m, a, r), now=NOW))

    def test_source_has_no_ledger_model_service_or_legacy_import(self):
        root = Path(__file__).parent
        banned = {'sqlite3', 'subprocess', 'keyring', 'requests', 'financial_datasets', 'provider_gateway', 'openai', 'expansion_wing', 'keychain_adapter'}
        for name in ('live_contract', 'credentials', 'transport', 'wire', 'qualification'):
            tree = ast.parse((root / ('provider_gateway_' + name + '.py')).read_text())
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(a.name.split('.')[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.add((node.module or '').split('.')[0])
            self.assertFalse(imports & banned)

    def test_receipt_correct_self_hash_wrong_parent_rejected(self):
        from provider_gateway_contract import content_hash
        from provider_gateway_live_contract import verify_qualification_receipt
        _, _, _, _, receipt = self.run_case()
        parents = dict(receipt['parents'])
        self.assertEqual(verify_qualification_receipt(receipt, content_hash(receipt), parents=parents), receipt)
        receipt['parents']['account'] = '0' * 64
        receipt['receipt_hash'] = content_hash({k: v for k, v in receipt.items() if k != 'receipt_hash'})
        with self.assertRaises(ValueError):
            verify_qualification_receipt(receipt, content_hash(receipt), parents=parents)

    def test_output_root_replacement_before_network_rejected(self):
        m, a, r = fixture()
        output = Path(m['root'])
        original = output.parent / 'preserved-original-output'
        fake, credentials = FakeNetwork(), FakeCredentials()
        def replace(service, account):
            if not original.exists():
                output.rename(original)
                output.mkdir(mode=0o700)
            return FAKE
        credentials.read = replace
        with self.assertRaises(ValueError):
            qualify(m, a, r, expected=pins(m, a, r), credential_backend=credentials, network=fake, clock=lambda: NOW)
        self.assertEqual(fake.calls, 0)
        self.assertEqual(list(output.iterdir()), [])
        self.assertTrue((original / 'ALPACA.reserved.json').exists())


class RecoveryTests(unittest.TestCase):
    def prepare(self, *, same_request=False):
        from provider_gateway_contract import content_hash
        m, a, r = fixture('MASSIVE')
        first = qualify(m, a, r, expected=pins(m, a, r), credential_backend=FakeCredentials(),
                        network=FakeNetwork(payload={'tickers': [{'ticker': 'MU'}]}), clock=lambda: NOW)
        root = Path(m['root'])
        if not same_request:
            next_m, next_a, _ = fixture('ALPACA')
            next_m['root'] = m['root']
            repin(next_m, next_a, r)
        else:
            next_m, next_a = m, a
        recovery = {'schema': 'iios-provider-recovery-v1',
                    'batch': {'batch_id': m['batch_id'], 'root': m['root'], 'scope': m['mode'],
                              'source_commit': m['source_commit'], 'runtime_parent': content_hash(r)},
                    'next_request': content_hash(next_m),
                    'entries': {'MASSIVE': {'request_id': content_hash(m), 'parents': pins(m, a, r),
                               'reservation_sha256': first['parents']['reservation'],
                               'receipt_sha256': content_hash(first),
                               'response_sha256': hashlib.sha256((root / 'MASSIVE.response.json').read_bytes()).hexdigest()}}}
        # Fixture anchors are captured from this known successful synthetic run,
        # before adversarial mutation. Production recovery never derives trust here.
        original = root.parent / 'trusted-originals'
        original.mkdir(mode=0o700)
        for path in root.iterdir():
            if path.is_file():
                (original / path.name).write_bytes(path.read_bytes())
        return next_m, next_a, r, recovery, content_hash(recovery), first

    def invoke(self, case):
        m, a, r, recovery, expected_recovery, _ = case
        credentials, network = FakeCredentials(), FakeNetwork()
        result = None
        blocked = False
        try:
            result = qualify(m, a, r, expected=pins(m, a, r), credential_backend=credentials,
                             network=network, clock=lambda: NOW, recovery=recovery,
                             expected_recovery=expected_recovery)
        except ValueError:
            blocked = True
        return blocked, credentials.calls, network.calls, result

    def assert_blocked(self, case):
        root = Path(case[0]['root'])
        reservations = {p.name: p.read_bytes() for p in root.glob('*.reserved.json')}
        blocked, credentials, network, _ = self.invoke(case)
        self.assertTrue(blocked)
        self.assertEqual(credentials, [])
        self.assertEqual(network, 0)
        for name, raw in reservations.items():
            self.assertEqual((root / name).read_bytes(), raw, 'consumed budget must remain unchanged')
        self.assertFalse((root / 'ALPACA.reserved.json').exists())

    def rewrite(self, case, name, mutate):
        path = Path(case[0]['root']) / name
        value = json.loads(path.read_text())
        mutate(value)
        from provider_gateway_contract import canonical
        path.chmod(0o600)
        path.write_bytes(canonical(value))
        path.chmod(0o400)

    def test_exact_demonstrated_defect_zero_dispatch(self):
        m, a, r = fixture('ALPACA')
        root = Path(m['root'])
        for name, value in {'MASSIVE.reserved.json': {}, 'MASSIVE.receipt.json': {'result': 'OBSERVED'}}.items():
            path = root / name
            path.write_text(json.dumps(value))
            path.chmod(0o400)
        self.assert_blocked((m, a, r, None, None, None))

    def test_status_only_with_all_files_still_has_no_authority(self):
        case = self.prepare()
        self.rewrite(case, 'MASSIVE.receipt.json', lambda v: (v.clear(), v.update({'result': 'OBSERVED'})))
        self.assert_blocked(case)

    def test_missing_recovery_or_independent_hash(self):
        case = self.prepare()
        for recovery, expected in ((None, None), (case[3], None), (None, case[4])):
            with self.subTest(recovery=recovery is not None, expected=expected is not None):
                self.assert_blocked((*case[:3], recovery, expected, case[5]))

    def test_receipt_content_and_hash_tampering(self):
        for field, value in (('result', 'UNVERIFIED'), ('receipt_hash', '0' * 64), ('http_status', 201)):
            case = self.prepare()
            self.rewrite(case, 'MASSIVE.receipt.json', lambda v: v.update({field: value}))
            with self.subTest(field=field):
                self.assert_blocked(case)

    def test_self_consistent_forgery_cannot_replace_independent_hash(self):
        from provider_gateway_contract import content_hash
        case = self.prepare()
        def forge(v):
            v['parents']['account'] = '0' * 64
            v['receipt_hash'] = content_hash({k: x for k, x in v.items() if k != 'receipt_hash'})
        self.rewrite(case, 'MASSIVE.receipt.json', forge)
        self.assert_blocked(case)
        # Nor may disk-derived receipt pins silently replace the trusted envelope.
        case[3]['entries']['MASSIVE']['receipt_sha256'] = content_hash(json.loads((Path(case[0]['root']) / 'MASSIVE.receipt.json').read_text()))
        self.assert_blocked(case)

    def test_missing_or_wrong_reservation_parents(self):
        from provider_gateway_contract import content_hash
        for missing in (True, False):
            case = self.prepare()
            def mutate(v):
                if missing:
                    v.pop('parents')
                else:
                    v['parents']['manifest'] = '0' * 64
            self.rewrite(case, 'MASSIVE.reserved.json', mutate)
            self.assert_blocked(case)
            # Even an independently repinned envelope cannot make wrong parents valid.
            entry = case[3]['entries']['MASSIVE']
            entry['reservation_sha256'] = hashlib.sha256((Path(case[0]['root']) / 'MASSIVE.reserved.json').read_bytes()).hexdigest()
            self.assert_blocked((*case[:4], content_hash(case[3]), case[5]))

    def test_replay_request_provider_batch_and_root(self):
        from provider_gateway_contract import content_hash
        for field, value in (('request_id', '0' * 64), ('provider', 'ALPACA'), ('batch_id', 'another-batch'), ('root', '/synthetic-other-root'), ('scope', 'LIVE_QUALIFICATION')):
            case = self.prepare()
            def mutate(v):
                v[field] = value
                v['receipt_hash'] = content_hash({k: x for k, x in v.items() if k != 'receipt_hash'})
            self.rewrite(case, 'MASSIVE.receipt.json', mutate)
            # Re-pin receipt bytes in an otherwise trusted envelope to ensure the
            # semantic identity checks also reject replay, independently of hashes.
            case[3]['entries']['MASSIVE']['receipt_sha256'] = hashlib.sha256((Path(case[0]['root']) / 'MASSIVE.receipt.json').read_bytes()).hexdigest()
            with self.subTest(field=field):
                self.assert_blocked((*case[:4], content_hash(case[3]), case[5]))

    def test_recovery_envelope_bound_to_exact_next_request_and_batch(self):
        from provider_gateway_contract import content_hash
        for field in ('next_request', 'batch_id'):
            case = self.prepare()
            if field == 'next_request':
                case[3][field] = '0' * 64
            else:
                case[3]['batch'][field] = 'another-batch'
            self.assert_blocked((*case[:4], content_hash(case[3]), case[5]))

    def test_missing_each_recovery_artifact(self):
        for suffix in ('reserved', 'receipt', 'response'):
            case = self.prepare()
            path = Path(case[0]['root']) / ('MASSIVE.' + suffix + '.json')
            path.rename(path.with_suffix('.json.preserved-missing'))
            self.assert_blocked(case)

    def test_malformed_record_and_response_tamper(self):
        for kind in ('malformed', 'response'):
            case = self.prepare()
            path = Path(case[0]['root']) / ('MASSIVE.receipt.json' if kind == 'malformed' else 'MASSIVE.response.json')
            path.chmod(0o600)
            path.write_bytes(b'{malformed' if kind == 'malformed' else b'{}')
            path.chmod(0o400)
            self.assert_blocked(case)

    def test_missing_extra_recovery_members(self):
        from provider_gateway_contract import content_hash
        for kind in ('missing', 'extra'):
            case = self.prepare()
            if kind == 'missing':
                case[3]['entries'].clear()
            else:
                case[3]['entries']['ALPACA'] = dict(case[3]['entries']['MASSIVE'])
            self.assert_blocked((*case[:4], content_hash(case[3]), case[5]))

    def test_ambiguous_reservation_never_released(self):
        m, a, r = fixture('ALPACA')
        first = qualify(m, a, r, expected=pins(m, a, r), credential_backend=FakeCredentials(), network=FakeNetwork(failure=True), clock=lambda: NOW)
        path = Path(m['root']) / 'ALPACA.reserved.json'
        before = path.read_bytes()
        blocked, credentials, calls, _ = self.invoke((m, a, r, None, None, first))
        self.assertTrue(blocked)
        self.assertEqual((credentials, calls), ([], 0))
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue((path.parent / 'STOP.json').exists())

    def test_valid_recovery_permits_next_provider_once(self):
        case = self.prepare()
        blocked, credentials, calls, receipt = self.invoke(case)
        self.assertFalse(blocked)
        self.assertEqual(len(credentials), 2)
        self.assertEqual(calls, 1)
        self.assertEqual(receipt['result'], 'OBSERVED')
        self.assertEqual(receipt['recovery_parent'], case[4])
        # Reusing the old recovery envelope omits the newly consumed provider slot.
        blocked, credentials, calls, _ = self.invoke(case)
        self.assertTrue(blocked)
        self.assertEqual((credentials, calls), ([], 0))

    def test_valid_same_request_recovery_returns_original_without_dispatch(self):
        case = self.prepare(same_request=True)
        before = {p.name: p.read_bytes() for p in Path(case[0]['root']).iterdir()}
        for _ in range(2):
            blocked, credentials, calls, receipt = self.invoke(case)
            self.assertFalse(blocked)
            self.assertEqual((credentials, calls), ([], 0))
            self.assertEqual(receipt, case[5])
        self.assertEqual(before, {p.name: p.read_bytes() for p in Path(case[0]['root']).iterdir()})

    def test_prior_provider_cannot_replay_as_new_request(self):
        from provider_gateway_contract import content_hash
        case = self.prepare(same_request=True)
        case[0]['maximum_age_seconds'] += 1
        case[3]['next_request'] = content_hash(case[0])
        self.assert_blocked((*case[:4], content_hash(case[3]), case[5]))

    def test_correct_hash_wrong_receipt_and_response_parents(self):
        from provider_gateway_contract import content_hash
        for suffix in ('receipt', 'response'):
            case = self.prepare()
            def mutate(v):
                v['parents']['reservation'] = '0' * 64
                if suffix == 'receipt':
                    v['receipt_hash'] = content_hash({k: x for k, x in v.items() if k != 'receipt_hash'})
            self.rewrite(case, 'MASSIVE.' + suffix + '.json', mutate)
            case[3]['entries']['MASSIVE'][suffix + '_sha256'] = hashlib.sha256((Path(case[0]['root']) / ('MASSIVE.' + suffix + '.json')).read_bytes()).hexdigest()
            self.assert_blocked((*case[:4], content_hash(case[3]), case[5]))

    def test_response_bytes_and_observation_hash_mismatch(self):
        from provider_gateway_contract import content_hash
        for field in ('raw_response_sha256', 'normalized_sha256'):
            case = self.prepare()
            def mutate(v):
                v[field] = '0' * 64
                v['receipt_hash'] = content_hash({k: x for k, x in v.items() if k != 'receipt_hash'})
            self.rewrite(case, 'MASSIVE.receipt.json', mutate)
            case[3]['entries']['MASSIVE']['receipt_sha256'] = hashlib.sha256((Path(case[0]['root']) / 'MASSIVE.receipt.json').read_bytes()).hexdigest()
            self.assert_blocked((*case[:4], content_hash(case[3]), case[5]))

    def test_recovery_symlink_and_hardlink_rejected(self):
        for kind in ('symlink', 'hardlink'):
            case = self.prepare()
            path = Path(case[0]['root']) / 'MASSIVE.receipt.json'
            preserved = path.with_suffix('.json.preserved-original')
            path.rename(preserved)
            if kind == 'symlink':
                path.symlink_to(preserved)
            else:
                os.link(preserved, path)
            self.assert_blocked(case)

    def test_exact_missing_and_malformed_pin_schema(self):
        from provider_gateway_contract import content_hash
        for field in ('reservation_sha256', 'receipt_sha256', 'response_sha256', 'parents'):
            case = self.prepare()
            del case[3]['entries']['MASSIVE'][field]
            self.assert_blocked((*case[:4], content_hash(case[3]), case[5]))

    def test_missing_all_prior_artifacts_cannot_reset_existing_batch(self):
        case = self.prepare()
        root = Path(case[0]['root'])
        for suffix in ('reserved', 'receipt', 'response'):
            path = root / ('MASSIVE.' + suffix + '.json')
            path.rename(path.with_suffix('.json.preserved-missing'))
        self.assert_blocked((*case[:3], None, None, case[5]))
        self.assert_blocked(case)


class AlphaQuoteQualificationTests(unittest.TestCase):
    def execute_quote(self, network):
        from test_provider_gateway_live_contract import quote_fixture
        m, a, r = quote_fixture()
        credentials = FakeCredentials()
        receipt = qualify(m, a, r, expected=pins(m, a, r), credential_backend=credentials, network=network, clock=lambda: NOW)
        self.assertEqual(network.calls, 1)
        self.assertEqual(len(credentials.calls), 1)
        self.assertEqual(receipt['retry_count'], 0)
        self.assertTrue(all(v is False for v in receipt['authority'].values()))
        self.assertEqual(receipt['parents']['manifest'], pins(m, a, r)['manifest'])
        for path in Path(m['root']).iterdir():
            self.assertNotIn(FAKE, path.read_bytes())
        return m, a, r, receipt

    def test_disposable_runtime_quote_end_to_end_no_readiness_upgrade(self):
        from test_provider_gateway_wire import global_quote
        m, a, r, receipt = self.execute_quote(FakeNetwork(payload=global_quote()))
        self.assertEqual(receipt['result'], 'OBSERVED')
        self.assertEqual(receipt['observations']['response_realtime_entitlement'], 'UNVERIFIED')
        self.assertEqual(receipt['billing'], 'UNVERIFIED')
        self.assertEqual(receipt['provider_readiness'], 'NOT_READY')
        verify_runtime(admit(m, a, r, expected=pins(m, a, r), now=NOW))

    def test_failures_retain_reservation_without_retry(self):
        from test_provider_gateway_wire import global_quote
        escaped = ''.join('\\u%04x' % byte for byte in FAKE)
        networks = [FakeNetwork(failure=True)]
        networks += [FakeNetwork(status=status) for status in (301, 302, 307, 308, 401, 403, 429, 500)]
        networks += [FakeNetwork(payload={key: 'synthetic'}) for key in ('Note', 'Information', 'Error Message')]
        networks += [FakeNetwork(raw=raw) for raw in (b'{bad', b' ' * 100001, b'{"Global Quote":{},"Global Quote":{}}', ('{"name":"' + escaped + '"}').encode())]
        networks += [FakeNetwork(payload={'value': FAKE.decode()})]
        for network in networks:
            m, a, r, receipt = self.execute_quote(network)
            self.assertEqual(receipt['result'], 'AMBIGUOUS_OR_UNVERIFIED_STOP')
            self.assertIsNone(receipt['raw_response_sha256'])
            self.assertTrue((Path(m['root']) / 'ALPHA_VANTAGE.reserved.json').exists())
            with self.assertRaises(ValueError):
                qualify(m, a, r, expected=pins(m, a, r), credential_backend=FakeCredentials(), network=network, clock=lambda: NOW)
            self.assertEqual(network.calls, 1)
