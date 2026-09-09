from datetime import datetime, timedelta, timezone
import json
import unittest

from .financial_datasets import API_HOST, AUTH_HEADER, KEYCHAIN_ACCOUNT, KEYCHAIN_SERVICE
from .provider_readiness import COST_SCHEMA, ENDPOINT_PATHS, OFFICIAL_SOURCES, PRICING_OBSERVATION_IDENTITY, PRIOR_SESSION_DATE, PROVIDER, SEPTEMBER_9_REQUIRED_COVERAGE_UTC, EndpointCost, FixedCredentialBoundary, FixtureAccounting, bounded_stub_request, classify_identity, evaluate_readiness, prior_market_session, revised_plan_identity, revised_request_plan, reviewed_cost_contracts, september_9_cost_evidence_document, september_9_plan_identity, september_9_request_plan, validate_september_9_cost_evidence
from .operational_market_executor_service import validate_september_9_readiness
from .unattended_tuesday import request_plan

NOW = datetime(2026, 9, 8, 2, tzinfo=timezone.utc)

class Probe:
    def __init__(self, value): self.value=value; self.calls=[]
    def exists(self, **kwargs): self.calls.append(kwargs); return self.value

class Transport:
    def __init__(self, result=None, error=None): self.result=result; self.error=error; self.calls=[]
    def send(self, **kwargs):
        self.calls.append(kwargs)
        if self.error: raise self.error
        return self.result

class Superbatch28A(unittest.TestCase):
    def contracts(self, credits=1, expiry=timedelta(days=1)):
        source="https://www.financialdatasets.ai/pricing"
        return {endpoint:EndpointCost(endpoint, endpoint, credits, source, NOW.isoformat(), (NOW+expiry).isoformat()) for endpoint in ENDPOINT_PATHS}

    def test_exact_provider_and_presence_only_selector(self):
        self.assertEqual((PROVIDER,API_HOST,AUTH_HEADER),("FINANCIAL_DATASETS","api.financialdatasets.ai","X-API-KEY"))
        probe=Probe(True); boundary=FixedCredentialBoundary(probe)
        self.assertEqual(boundary.status(),"AVAILABLE")
        self.assertEqual(probe.calls,[{"service":KEYCHAIN_SERVICE,"account":KEYCHAIN_ACCOUNT}])
        self.assertFalse(hasattr(boundary,"retrieve"))

    def test_revised_plan_is_fifty_supported_unique_identities(self):
        rows=revised_request_plan()
        self.assertEqual(len(rows),50)
        self.assertEqual(len({row["request_identity"] for row in rows}),50)
        self.assertEqual(sum(classify_identity(row)=="SUPPORTED_AND_COSTED" for row in rows),50)
        self.assertEqual(sum(row["endpoint"]=="COMPANY_FACTS" for row in rows),1)
        self.assertEqual(sum(row["evidence_category"]=="PRIOR_SESSION_BASELINE" for row in rows),9)
        self.assertTrue(all(row["date_window"]==f"{PRIOR_SESSION_DATE}/{PRIOR_SESSION_DATE}" for row in rows if row["evidence_category"]=="PRIOR_SESSION_BASELINE"))
        result=evaluate_readiness(self.contracts(),FixedCredentialBoundary(Probe(True)),now=NOW)
        self.assertEqual((result["provider_state"],result["failure_category"]),("READY","PROVIDER_READY"))
        self.assertEqual((result["supported_costed_identity_count"],result["unsupported_identity_count"]),(50,0))
        self.assertEqual((result["worst_case_stage_a_credits"],result["stage_a_safety_margin"]),(50,50))
        self.assertEqual(result["stage_a_released_credits"],0)
        self.assertNotIn("request_plan_identity",result)
        self.assertEqual(len(revised_plan_identity()),64)

    def test_prior_session_skips_weekend_and_closed_holiday(self):
        self.assertEqual(prior_market_session("2026-09-08"),"2026-09-04")
        self.assertEqual(prior_market_session("2026-09-07"),"2026-09-04")
        self.assertEqual(prior_market_session("2026-09-06"),"2026-09-04")

    def test_september_9_plan_and_cost_evidence_are_separate_and_nonspending(self):
        rows=september_9_request_plan()
        self.assertEqual((len(rows),len({r['identity'] for r in rows}),sum(r['cost'] for r in rows)),(50,50,50))
        self.assertTrue(all(r['session_date']=='2026-09-09' and r['retry'] is False for r in rows))
        self.assertFalse({r['identity'] for r in rows}&{r['request_identity'] for r in revised_request_plan()})
        observed='2026-09-09T12:00:00+00:00'; expires='2026-09-09T20:05:00+00:00'
        doc=september_9_cost_evidence_document(observed_at=observed,expires_at=expires,
            observation_identity='financial-datasets-pricing-2026-09-09-review-v1')
        self.assertEqual(validate_september_9_cost_evidence(doc,now=datetime(2026,9,9,13,tzinfo=timezone.utc)),doc)
        self.assertEqual(doc['request_plan_identity'],september_9_plan_identity())
        self.assertNotIn(doc['request_plan_identity'],{'d08262228104ee464d602688aae6e1c97e67db10e640233deff87a1231e63c23','c40b4c241d114df4d95069e55e7c68a4fbc8e1c899c5faa6aa8e3767b97a626a'})
        self.assertEqual((doc['unique_request_identity_count'],doc['automatic_retry_count']),(50,0))
        self.assertEqual(doc['reviewed_endpoint_identities'],sorted(ENDPOINT_PATHS))
        self.assertEqual(doc['required_session_coverage_utc'],SEPTEMBER_9_REQUIRED_COVERAGE_UTC)
        self.assertFalse(doc['browser_refresh']); self.assertFalse(doc['provider_execution_refresh'])
        self.assertEqual(validate_september_9_readiness(observed_at=observed,expires_at=expires,
            observation_identity='financial-datasets-pricing-2026-09-09-review-v1',
            command_time=datetime(2026,9,9,13,tzinfo=timezone.utc)),'SEPTEMBER_9_READINESS_VALIDATED_NOT_INSTALLED')

    def test_september_9_cost_evidence_fails_closed_when_stale_or_short(self):
        with self.assertRaisesRegex(ValueError,'SEPTEMBER_9_COST_EVIDENCE_INVALID'):
            september_9_cost_evidence_document(observed_at='2026-09-08T12:00:00+00:00',
                expires_at='2026-09-09T12:00:00+00:00',
                observation_identity='financial-datasets-pricing-2026-09-09-review-v1')

    def test_old_instrument_profile_remains_a_negative_classification(self):
        old=[row for row in request_plan("tuesday-2026-09-08-stage-a") if row["endpoint"]=="INSTRUMENT_PROFILE"]
        self.assertEqual(len(old),9)
        self.assertTrue(all(classify_identity(dict(row,provider_contract="fd-stage-a-standard-v1"))=="UNSUPPORTED_FOR_INSTRUMENT" for row in old))

    def test_integer_cost_hash_expiry_and_unknown(self):
        contract=next(iter(self.contracts().values()))
        self.assertEqual(contract.document()["schema"],COST_SCHEMA); self.assertEqual(contract.validate(NOW),"VALID")
        self.assertEqual(len(contract.document()["canonical_content_hash"]),64)
        source="https://www.financialdatasets.ai/pricing"
        self.assertEqual(EndpointCost("x","MARKET_SNAPSHOT",0,source,NOW.isoformat(),(NOW+timedelta(1)).isoformat()).validate(NOW),"ENDPOINT_COST_UNKNOWN")
        self.assertEqual(EndpointCost("x","MARKET_SNAPSHOT",1,source,(NOW-timedelta(2)).isoformat(),(NOW-timedelta(1)).isoformat()).validate(NOW),"COST_CONTRACT_EXPIRED")
        changed=EndpointCost("x","MARKET_SNAPSHOT",1,source,NOW.isoformat(),(NOW+timedelta(1)).isoformat(),pricing_observation_identity="changed")
        self.assertEqual(changed.validate(NOW),"ENDPOINT_COST_UNKNOWN")
        self.assertEqual(PRICING_OBSERVATION_IDENTITY,"financial-datasets-pricing-2026-09-08-v1")
        self.assertEqual(set(reviewed_cost_contracts()),set(ENDPOINT_PATHS))
        self.assertTrue(all(contract.validate(NOW)=="VALID" for contract in reviewed_cost_contracts().values()))

    def test_browser_projection_leaks_no_selector_or_source(self):
        result=evaluate_readiness({},FixedCredentialBoundary(Probe(False)),now=NOW); text=json.dumps(result)
        for forbidden in (KEYCHAIN_SERVICE,KEYCHAIN_ACCOUNT,"https://","content_hash","credential_value"):
            self.assertNotIn(forbidden,text)
        self.assertFalse(result["network_enabled"]); self.assertTrue(result["authority_locked"])

    def test_missing_and_ambiguous_credentials_fail_closed(self):
        missing=evaluate_readiness(self.contracts(),FixedCredentialBoundary(Probe(False)),now=NOW)
        ambiguous=evaluate_readiness(self.contracts(),FixedCredentialBoundary(Probe(None)),now=NOW)
        self.assertEqual(missing["failure_category"],"CREDENTIAL_NOT_AVAILABLE")
        self.assertEqual(ambiguous["failure_category"],"CREDENTIAL_AMBIGUOUS")

    def test_unknown_expired_and_budget_overflow_fail_closed(self):
        unknown=evaluate_readiness({},FixedCredentialBoundary(Probe(True)),now=NOW)
        expired=evaluate_readiness(self.contracts(expiry=timedelta(seconds=-1)),FixedCredentialBoundary(Probe(True)),now=NOW)
        overflow=evaluate_readiness(self.contracts(credits=3),FixedCredentialBoundary(Probe(True)),now=NOW)
        self.assertEqual(unknown["failure_category"],"ENDPOINT_COST_UNKNOWN")
        self.assertEqual(expired["failure_category"],"COST_CONTRACT_EXPIRED")
        self.assertEqual(overflow["failure_category"],"BUDGET_INSUFFICIENT")
        self.assertEqual(overflow["stage_a_safety_margin"],-50)

    def test_fixed_stub_transport_and_ambiguous_no_retry(self):
        secret=b"synthetic-test-key-opaque"
        transport=Transport((200,"application/json; charset=utf-8",b'{"ticker":"MU"}'))
        result=bounded_stub_request(endpoint="COMPANY_FACTS",credential_supplier=lambda:secret,transport=transport)
        self.assertEqual(result["status_category"],"HTTP_2XX"); self.assertEqual(len(transport.calls),1)
        call=transport.calls[0]
        self.assertEqual((call["host"],call["path"],tuple(call["headers"])),(API_HOST,"/company/facts",(AUTH_HEADER,)))
        timed=Transport(error=TimeoutError())
        with self.assertRaisesRegex(ValueError,"AMBIGUOUS_CHARGE_NO_RETRY"):
            bounded_stub_request(endpoint="MARKET_SNAPSHOT",credential_supplier=lambda:secret,transport=timed)
        self.assertEqual(len(timed.calls),1)

    def test_stub_rejects_arbitrary_endpoint_content_type_and_size(self):
        secret=b"synthetic-test-key"
        with self.assertRaisesRegex(ValueError,"ENDPOINT_NOT_ALLOWED"):
            bounded_stub_request(endpoint="https://evil.invalid",credential_supplier=lambda:secret,transport=Transport())
        for result,category in [((200,"text/html",b"{}"),"CONTENT_TYPE_REJECTED"),((200,"application/json",b"x"*1_048_577),"RESPONSE_BOUNDS_EXCEEDED")]:
            with self.assertRaisesRegex(ValueError,category) as caught:
                bounded_stub_request(endpoint="COMPANY_FACTS",credential_supplier=lambda:secret,transport=Transport(result))
            self.assertNotIn("synthetic-test-key",str(caught.exception))

    def test_fixture_accounting_cache_duplicate_ambiguous_restart_and_close(self):
        rows=revised_request_plan(); accounting=FixtureAccounting.empty(); accounting.release(100)
        self.assertEqual(accounting.execute(rows[0]["request_identity"],"CONFIRMED"),"CONFIRMED")
        self.assertEqual(accounting.execute(rows[0]["request_identity"],"CONFIRMED"),"CACHE_HIT_ZERO_INCREMENTAL_COST")
        self.assertEqual(accounting.execute(rows[1]["request_identity"],"AMBIGUOUS"),"AMBIGUOUS_CHARGED_ONCE_NO_RETRY")
        with self.assertRaisesRegex(ValueError,"DUPLICATE_REQUEST_REJECTED"):
            accounting.execute(rows[1]["request_identity"],"CONFIRMED")
        restarted=FixtureAccounting(set(accounting.transmitted),dict(accounting.charged),set(accounting.cached),accounting.released_allowance)
        self.assertEqual(restarted.execute(rows[2]["request_identity"],"PRE_TRANSMISSION_REJECTED"),"PRE_TRANSMISSION_REJECTED")
        for row in rows[2:]: restarted.execute(row["request_identity"],"CONFIRMED")
        self.assertEqual((len(restarted.transmitted),sum(restarted.charged.values())),(50,50))
        restarted.close(); self.assertEqual(restarted.released_allowance,0)

if __name__ == "__main__": unittest.main()
