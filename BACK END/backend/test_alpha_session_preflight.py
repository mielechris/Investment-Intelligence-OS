"""CLI preflight with disposable fixtures; no native or provider invocation."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime as RealDatetime
import io
import json
import unittest
from unittest.mock import patch

from alpha_session_preflight import main, evaluate_bundle
from provider_gateway_contract import canonical, content_hash
import test_alpha_session_evidence as evidence_fixtures


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.fixture=evidence_fixtures.CandidateEvidenceTests(); self.fixture.setUp()
        outer=self.fixture; f=outer.fixture
        inputs=f.kwargs(); self.now=inputs.pop('now')
        self.bundle=dict(schema='iios-alpha-preflight-input-v1',candidate=outer.candidate,
                         candidate_hash=content_hash(outer.candidate),plan=f.plan,account=f.account,
                         runtime=f.runtime,allowance=f.allowance,runtime_manifest=outer.runtime_manifest,
                         claims_manifest=outer.claims_manifest,claims_manifest_hash=outer.claims_pin,
                         package_inputs=inputs)
        self.root=outer.base/'input'; self.root.mkdir()
        row=evidence_fixtures.write(self.root,'admission-input.json',canonical(self.bundle))
        self.root.chmod(0o500)
        self.args=['--input-root',str(self.root),'--expected-sha256',row['sha256'],
                   '--expected-bytes',str(row['size']),'--approved-runtime-root',str(outer.runtime_root),
                   '--approved-claims-root',str(outer.claims_root)]

    def tearDown(self): self.fixture.tearDown()

    def run_cli(self,args=None):
        stream=io.StringIO()
        with redirect_stdout(stream),patch('subprocess.run',side_effect=AssertionError('NO_LAUNCH')):
            result=main(self.args if args is None else args)
        return result,json.loads(stream.getvalue())

    def test_complete_files_still_blocked(self):
        stamp=self.now
        class Clock(RealDatetime):
            @classmethod
            def now(cls,tz=None): return stamp
        with patch('alpha_session_preflight.datetime',Clock):
            code,result=self.run_cli()
        self.assertEqual(code,2); self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(result['candidate_evidence'],'FILES_AND_BINDINGS_VERIFIED_ONLY')
        self.assertFalse(result['execution_authorized'])
        self.assertIn('OS_CONFINEMENT',result['pending'])

    def test_wrong_bundle_hash(self):
        args=list(self.args); args[3]='f'*64
        code,result=self.run_cli(args)
        self.assertEqual(code,1); self.assertEqual(result['candidate_evidence'],'FAILED')

    def test_embedded_clock_override_rejected(self):
        self.bundle['package_inputs']['now']=self.now.isoformat()
        with self.assertRaisesRegex(ValueError,'PREFLIGHT_INPUT_SCHEMA'):
            evaluate_bundle(self.bundle,now=self.now,approved_runtime_root=str(self.fixture.runtime_root),
                            approved_claims_root=str(self.fixture.claims_root))

    def test_unknown_execution_flag_rejected(self):
        with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as ctx:
            main(self.args+['--run'])
        self.assertEqual(ctx.exception.code,2)

    def test_missing_inputs_report_sanitized_blocker(self):
        args=list(self.args); args[1]=str(self.fixture.base/'absent')
        code,result=self.run_cli(args)
        self.assertEqual(code,1); self.assertEqual(result['failure'],'INPUT_UNAVAILABLE')
        self.assertNotIn(str(self.fixture.base),json.dumps(result))

    def test_roots_cannot_be_supplied_by_bundle(self):
        self.bundle['approved_runtime_root']=str(self.fixture.runtime_root)
        with self.assertRaisesRegex(ValueError,'PREFLIGHT_BUNDLE_SCHEMA'):
            evaluate_bundle(self.bundle,now=self.now,approved_runtime_root=str(self.fixture.runtime_root),
                            approved_claims_root=str(self.fixture.claims_root))


if __name__=='__main__': unittest.main()
