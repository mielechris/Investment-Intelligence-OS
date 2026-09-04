from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from expansion_wing.financial_datasets import (
    COMPANY_FACTS_SCHEMA_VERSION, FDCapability, FDPolicy, FDResponse, FinancialDatasetsAdapter,
)

NOW = datetime(2026, 9, 4, tzinfo=timezone.utc)


class Credentials:
    def retrieve(self) -> bytes: return b"synthetic-opaque-credential"


class Transport:
    def __init__(self, payload: object) -> None: self.payload = payload; self.calls = 0
    def trust_readiness(self) -> str: return "READY"
    def __call__(self, url, _headers, _tickers, _connect_timeout, _response_timeout):
        self.calls += 1
        return FDResponse(200, url, (), json.dumps(self.payload).encode())


def fetch(payload: object, tickers: tuple[str, ...] = ("MU",)):
    transport = Transport(payload)
    adapter = FinancialDatasetsAdapter(FDPolicy(enabled=True, provider_balance=1_000),
        credentials=Credentials(), transport=transport, utcnow=lambda: NOW, prior_ambiguous_credits=3)
    return adapter.fetch(FDCapability.COMPANY_FACTS, tickers), transport


class CompanyFactsV2ContractTests(unittest.TestCase):
    def test_official_wrapper_without_provider_timestamp_is_accepted(self):
        result, transport = fetch({"company_facts": {"ticker": "MU", "name": "Synthetic",
            "cik": "0000000001", "exchange": "NASDAQ", "is_active": True}})
        self.assertEqual((result.state, transport.calls), ("AVAILABLE", 1))
        record = result.records[0]
        self.assertEqual(record.schema_version, COMPANY_FACTS_SCHEMA_VERSION)
        self.assertIsNone(record.provider_publication_timestamp)
        self.assertEqual(record.freshness, "UNKNOWN")
        self.assertEqual((result.consumed_credits, result.remaining_credits), (4, 996))

    def test_documented_optional_fields_may_be_absent(self):
        result, _ = fetch({"company_facts": {"ticker": "MU"}})
        self.assertEqual(result.state, "AVAILABLE")

    def test_unknown_nested_values_are_observed_only_by_name_and_type(self):
        result, _ = fetch({"company_facts": {"ticker": "MU", "future_field": "private-value"}})
        self.assertEqual((result.state, result.ignored_field_count), ("AVAILABLE", 1))
        self.assertIn(("future_field", "string"), result.schema_observation)
        encoded = json.dumps(result.records[0].fields)
        self.assertNotIn("future_field", encoded); self.assertNotIn("private-value", encoded)
        self.assertNotIn("private-value", json.dumps(result.schema_observation))

    def test_ticker_envelope_and_cardinality_fail_closed(self):
        cases = (({"company_facts": {"ticker": "AMD"}}, ("MU",)),
            ({"company_facts": {"ticker": "MU"}, "extra": 1}, ("MU",)),
            ({"data": [{"ticker": "MU"}]}, ("MU",)))
        for payload, tickers in cases:
            with self.subTest(payload=payload, tickers=tickers):
                self.assertEqual(fetch(payload, tickers)[0].failure, "SCHEMA_REJECTED")

        result, transport = fetch({"company_facts": {"ticker": "MU"}}, ("MU", "AMD"))
        self.assertEqual((result.failure, transport.calls, result.consumed_credits), ("BATCH_LIMIT", 0, 3))

    def test_documented_types_and_sec_url_are_bounded(self):
        cases = ({"company_facts": {"ticker": "MU", "is_active": "true"}},
            {"company_facts": {"ticker": "MU", "name": None}},
            {"company_facts": {"ticker": "MU", "sec_filings_url": "http://www.sec.gov/x"}},
            {"company_facts": {"ticker": "MU", "sec_filings_url": "https://example.com/x"}})
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertEqual(fetch(payload)[0].failure, "SCHEMA_REJECTED")


if __name__ == "__main__": unittest.main()
