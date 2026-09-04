from __future__ import annotations

import json
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from expansion_wing.financial_datasets import (
    API_HOST, API_ORIGIN, AUTH_HEADER, AUTHORITY, ENDPOINTS, FMP_ACCOUNT, FMP_SERVICE, KEYCHAIN_ACCOUNT,
    KEYCHAIN_SERVICE, PROVIDER_ID, PROVIDER_NAME, CreditLedger, FDCapability, FDPolicy, FDResponse,
    FinancialDatasetsAdapter, SecurityFrameworkCredentialProvider, browser_readiness, enrich_shortlist,
    primary_source_gate, validate_credential, validate_origin,
)

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = json.loads((FIXTURES / "financial_datasets_mu_amd.json").read_text())
NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)
FIXTURE_CREDENTIAL = bytes([65]) * 32


class Credentials:
    def __init__(self, value=FIXTURE_CREDENTIAL, error=None): self.value=value; self.error=error; self.calls=0
    def retrieve(self):
        self.calls += 1
        if self.error: raise RuntimeError(self.error)
        return self.value


class Transport:
    def __init__(self, body, *, status=200, final_url=None, redirects=(), error=None, block=None):
        self.body = json.dumps(body).encode() if not isinstance(body, bytes) else body
        self.status=status; self.final_url=final_url; self.redirects=redirects; self.error=error
        self.block=block; self.calls=0; self.header_names=[]
    def __call__(self, url, headers, tickers, connect_timeout, response_timeout):
        self.calls += 1; self.header_names.append(tuple(headers));
        if self.block: self.block()
        if self.error: raise self.error
        return FDResponse(self.status, self.final_url or url, self.redirects, self.body)


def policy(**changes):
    return replace(FDPolicy(enabled=True, provider_balance=1_000), **changes)


def adapter_for(capability, fixture_key, **policy_changes):
    spec = ENDPOINTS[capability]
    transport = Transport(FIXTURE[fixture_key], final_url=f"{API_ORIGIN}{spec.path}")
    return FinancialDatasetsAdapter(policy(**policy_changes), credentials=Credentials(), transport=transport,
        utcnow=lambda: NOW), transport


class IdentityCredentialTests(unittest.TestCase):
    def test_provider_and_selector_are_distinct_from_fmp(self):
        self.assertEqual((PROVIDER_ID, PROVIDER_NAME, API_ORIGIN),
            ("FINANCIAL_DATASETS", "Financial Datasets", "https://api.financialdatasets.ai"))
        self.assertEqual((KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT),
            ("com.iios.expansion-wing.financial-datasets", "financial-datasets-api-key"))
        self.assertNotEqual((KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT), (FMP_SERVICE, FMP_ACCOUNT))

    def test_security_framework_provider_exact_selector_and_failures(self):
        class Adapter:
            service = KEYCHAIN_SERVICE.encode()
            def retrieve(self, account): self.account=account; return FIXTURE_CREDENTIAL
        source = Adapter(); self.assertEqual(SecurityFrameworkCredentialProvider(source).retrieve(), FIXTURE_CREDENTIAL)
        self.assertEqual(source.account, KEYCHAIN_ACCOUNT)
        source.service = FMP_SERVICE.encode()
        with self.assertRaises(ValueError): SecurityFrameworkCredentialProvider(source)
        for value in (b"", b"x" * 31, b"x" * 33, b"!" * 32):
            with self.subTest(length=len(value)), self.assertRaises(RuntimeError): validate_credential(value)

    def test_missing_ambiguous_inaccessible_context_are_sanitized(self):
        for category in ("KEY_RECORD_MISSING", "KEY_RECORD_INACCESSIBLE_OR_AMBIGUOUS", "INVALID_KEYCHAIN_QUERY", "other"):
            adapter = FinancialDatasetsAdapter(policy(), credentials=Credentials(error=category), transport=Transport({}))
            result = adapter.fetch(FDCapability.COMPANY_FACTS, ("MU", "AMD"))
            expected = category if category in {"KEY_RECORD_MISSING", "KEY_RECORD_INACCESSIBLE_OR_AMBIGUOUS", "INVALID_KEYCHAIN_QUERY"} else "KEYCHAIN_UNAVAILABLE"
            self.assertEqual(result.failure, expected)


class EndpointCapabilityTests(unittest.TestCase):
    def test_all_twenty_capabilities_are_explicit_and_machine_manifest_matches(self):
        manifest = json.loads((FIXTURES / "financial_datasets_capabilities.json").read_text())
        self.assertEqual(manifest["provider_id"], PROVIDER_ID); self.assertEqual(len(ENDPOINTS), 20)
        self.assertEqual(manifest["capabilities"], {item.value: spec.state for item, spec in ENDPOINTS.items()})
        self.assertTrue(all(spec.state in {"SUPPORTED", "PREMIUM_SUPPORTED", "CONTRACT_ONLY", "UNAVAILABLE", "LICENSE_REVIEW_REQUIRED"} for spec in ENDPOINTS.values()))

    def test_exact_https_origin_and_no_arbitrary_paths(self):
        self.assertEqual(validate_origin(f"{API_ORIGIN}/company/facts/"), "/company/facts/")
        rejected = ("http://api.financialdatasets.ai/company/facts/", "https://evil.api.financialdatasets.ai/company/facts/",
            "https://api.financialdatasets.ai:444/company/facts/", "https://user:pass@api.financialdatasets.ai/company/facts/",
            "https://127.0.0.1/company/facts/", "https://api.financialdatasets.ai/company/facts/?key=x")
        for url in rejected:
            with self.subTest(url=url), self.assertRaises(ValueError): validate_origin(url)
        blocked = FinancialDatasetsAdapter(policy(), credentials=Credentials(), transport=Transport({})).fetch(
            FDCapability.SEC_FILING_ITEM_METADATA, ("MU",))
        self.assertEqual(blocked.failure, "ENDPOINT_NOT_ALLOWED")

    def test_default_discovery_performs_zero_provider_or_credential_calls(self):
        credentials=Credentials(); transport=Transport({})
        result = FinancialDatasetsAdapter(credentials=credentials, transport=transport).fetch(FDCapability.COMPANY_FACTS, ("MU",))
        self.assertEqual(result.failure, "DISABLED"); self.assertEqual((credentials.calls, transport.calls), (0, 0))


class CreditTests(unittest.TestCase):
    def test_standard_premium_unknown_balance_and_unknown_cost(self):
        standard, _ = adapter_for(FDCapability.COMPANY_FACTS, "company_facts")
        result = standard.fetch(FDCapability.COMPANY_FACTS, ("MU", "AMD"))
        self.assertEqual((result.projected_credit_cost, result.consumed_credits, result.remaining_credits), (1, 1, 999))
        premium_payload = {"data":[{"ticker":"MU","report_period":"2026-Q2","updated_at":"2026-08-01T12:00:00Z","segments":[]} ]}
        premium = FinancialDatasetsAdapter(policy(), credentials=Credentials(), transport=Transport(premium_payload,
            final_url=f"{API_ORIGIN}{ENDPOINTS[FDCapability.SEGMENTED_FINANCIAL_STATEMENTS].path}"), utcnow=lambda: NOW)
        value = premium.fetch(FDCapability.SEGMENTED_FINANCIAL_STATEMENTS, ("MU",))
        self.assertEqual((value.projected_credit_cost, value.consumed_credits), (8, 8))
        unknown = FinancialDatasetsAdapter(replace(policy(), provider_balance=None), credentials=Credentials(), transport=Transport({}))
        self.assertEqual(unknown.fetch(FDCapability.COMPANY_FACTS, ("MU",)).failure, "BALANCE_UNKNOWN")
        with self.assertRaises(RuntimeError): CreditLedger(policy()).authorize_attempt(None)

    def test_hard_daily_monthly_ceiling_and_auto_reload(self):
        with self.assertRaises(ValueError): FDPolicy(total_ceiling=0).validate()
        with self.assertRaises(ValueError): FDPolicy(auto_reload=True).validate()
        ledger = CreditLedger(policy(total_ceiling=10, daily_ceiling=8, monthly_ceiling=9))
        ledger.authorize_attempt(8)
        with self.assertRaises(RuntimeError): ledger.authorize_attempt(1)

    def test_cache_and_singleflight_consume_no_additional_credit(self):
        entered=threading.Event(); release=threading.Event()
        def block(): entered.set(); release.wait(2)
        spec=ENDPOINTS[FDCapability.COMPANY_FACTS]; transport=Transport(FIXTURE["company_facts"],
            final_url=f"{API_ORIGIN}{spec.path}", block=block)
        adapter=FinancialDatasetsAdapter(policy(), credentials=Credentials(), transport=transport, utcnow=lambda: NOW)
        results=[]
        first=threading.Thread(target=lambda: results.append(adapter.fetch(FDCapability.COMPANY_FACTS, ("MU","AMD"))))
        second=threading.Thread(target=lambda: results.append(adapter.fetch(FDCapability.COMPANY_FACTS, ("MU","AMD"))))
        first.start(); entered.wait(1); second.start(); release.set(); first.join(); second.join()
        self.assertEqual((transport.calls, adapter.credits.consumed), (1,1)); self.assertEqual(sum(x.cache_hit for x in results),1)
        cached=adapter.fetch(FDCapability.COMPANY_FACTS, ("MU","AMD"))
        self.assertTrue(cached.cache_hit); self.assertEqual(adapter.credits.consumed,1)

    def test_retry_attempts_each_consume_credit_but_terminal_does_not_retry(self):
        spec=ENDPOINTS[FDCapability.COMPANY_FACTS]
        transient=Transport({}, status=500, final_url=f"{API_ORIGIN}{spec.path}")
        adapter=FinancialDatasetsAdapter(policy(retry_limit=1), credentials=Credentials(), transport=transient)
        adapter.fetch(FDCapability.COMPANY_FACTS, ("MU",)); self.assertEqual((transient.calls, adapter.credits.consumed),(2,2))
        auth=Transport({}, status=401, final_url=f"{API_ORIGIN}{spec.path}")
        adapter=FinancialDatasetsAdapter(policy(retry_limit=1), credentials=Credentials(), transport=auth)
        self.assertEqual(adapter.fetch(FDCapability.COMPANY_FACTS, ("MU",)).failure,"AUTHENTICATION_FAILED")
        self.assertEqual((auth.calls, adapter.credits.consumed),(1,1))


class FixtureNormalizationTests(unittest.TestCase):
    def test_mu_amd_facts_schema_provenance_ignored_fields_and_secret_containment(self):
        adapter, transport=adapter_for(FDCapability.COMPANY_FACTS,"company_facts")
        result=adapter.fetch(FDCapability.COMPANY_FACTS,("MU","AMD")); self.assertEqual(result.state,"AVAILABLE")
        self.assertEqual({r.ticker for r in result.records},{"MU","AMD"}); self.assertEqual(result.ignored_field_count,1)
        self.assertTrue(all(r.provider_id==PROVIDER_ID and r.schema_version and r.verification_state=="PRIMARY_SOURCE_REQUIRED" for r in result.records))
        safe=json.dumps(result.safe_accounting(),sort_keys=True); self.assertNotIn(FIXTURE_CREDENTIAL.decode(),safe)
        self.assertEqual(transport.header_names,[(AUTH_HEADER,)])

    def test_statement_price_filing_and_earnings_classifications_remain_distinct(self):
        cases=((FDCapability.INCOME_STATEMENTS,"income_statements","PROVIDER_NORMALIZED_FACT"),
            (FDCapability.REAL_TIME_PRICE_SNAPSHOT,"price_snapshot","TECHNICAL_OBSERVATION"),
            (FDCapability.SEC_FILING_METADATA,"filing_metadata","PRIMARY_SOURCE_FACT"),
            (FDCapability.EARNINGS,"earnings","ANALYST_ESTIMATE"))
        for capability,key,classification in cases:
            with self.subTest(capability=capability):
                adapter,_=adapter_for(capability,key); result=adapter.fetch(capability,("MU","AMD"))
                self.assertEqual({record.data_classification for record in result.records},{classification})

    def test_stale_future_schema_oversize_timeout_and_redirect_fail_closed(self):
        spec=ENDPOINTS[FDCapability.COMPANY_FACTS]
        stale=FinancialDatasetsAdapter(policy(),credentials=Credentials(),transport=Transport(
            FIXTURE["company_facts"],final_url=f"{API_ORIGIN}{spec.path}"),
            utcnow=lambda:datetime(2026,8,4,tzinfo=timezone.utc))
        self.assertTrue(all(r.freshness=="STALE" for r in stale.fetch(FDCapability.COMPANY_FACTS,("MU","AMD")).records))
        future_body={"data":[{"ticker":"MU","name":"Synthetic","updated_at":"2026-08-03T12:00:00Z"}]}
        future=FinancialDatasetsAdapter(policy(),credentials=Credentials(),transport=Transport(future_body,final_url=f"{API_ORIGIN}{spec.path}"),utcnow=lambda:NOW)
        self.assertEqual(future.fetch(FDCapability.COMPANY_FACTS,("MU",)).failure,"POINT_IN_TIME_REJECTED")
        malformed=FinancialDatasetsAdapter(policy(),credentials=Credentials(),transport=Transport({"wrong":[]},final_url=f"{API_ORIGIN}{spec.path}"),utcnow=lambda:NOW)
        self.assertEqual(malformed.fetch(FDCapability.COMPANY_FACTS,("MU",)).failure,"SCHEMA_REJECTED")
        oversized=FinancialDatasetsAdapter(policy(response_size_limit=10),credentials=Credentials(),transport=Transport(b"x"*11,final_url=f"{API_ORIGIN}{spec.path}"))
        self.assertEqual(oversized.fetch(FDCapability.COMPANY_FACTS,("MU",)).failure,"RESPONSE_TOO_LARGE")
        timed=FinancialDatasetsAdapter(policy(retry_limit=0),credentials=Credentials(),transport=Transport({},error=TimeoutError()))
        self.assertEqual(timed.fetch(FDCapability.COMPANY_FACTS,("MU",)).failure,"TIMEOUT")
        redirect=FinancialDatasetsAdapter(policy(),credentials=Credentials(),transport=Transport({},final_url="https://other.example/company/facts/"))
        self.assertEqual(redirect.fetch(FDCapability.COMPANY_FACTS,("MU",)).failure,"REDIRECT_REJECTED")

    def test_batch_limit_partial_outage_no_substitution_and_primary_gate(self):
        adapter,_=adapter_for(FDCapability.COMPANY_FACTS,"company_facts")
        self.assertEqual(adapter.fetch(FDCapability.COMPANY_FACTS,tuple(f"X{i}" for i in range(51))).failure,"BATCH_LIMIT")
        packet=enrich_shortlist(adapter,(FDCapability.COMPANY_FACTS,FDCapability.COMPANY_NEWS_METADATA),("MU","AMD"))
        self.assertEqual(packet["state"],"PARTIAL"); self.assertTrue(packet["partial_outage_visible"])
        self.assertFalse(packet["cross_provider_substitution"]); self.assertTrue(all(v is False for v in packet["authority"].values()))
        blocked=primary_source_gate(packet["results"][0].records[0],primary_source_verified=False,human_approved=True)
        self.assertEqual(blocked["status"],"BLOCKED_PRIMARY_SOURCE_VERIFICATION"); self.assertFalse(blocked["paper_position_proposal"])

    def test_browser_projection_is_scalar_and_private_free(self):
        value=browser_readiness(); self.assertEqual(value["credential"],"NOT_PROVISIONED")
        self.assertEqual(value["provider_network"],"DISABLED"); self.assertEqual(value["credit_ceiling"],1000)
        self.assertFalse(value["auto_reload"] or value["continuous_scanning"] or value["provider_authority_granted"])
        encoded=json.dumps(value); self.assertNotIn(KEYCHAIN_SERVICE,encoded); self.assertNotIn(API_ORIGIN,encoded)


if __name__ == "__main__": unittest.main()
