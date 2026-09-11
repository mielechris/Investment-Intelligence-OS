"""Gateway tests with synthetic inputs and in-process injected transports only."""
import ast
import contextlib
import io
import json
from pathlib import Path
import unittest

from provider_gateway import ProviderGateway, QUALIFICATIONS, governed_flow
from provider_gateway_contract import content_hash, locked_authority, readiness

NOW = "2026-09-14T13:30:30+00:00"
STAMP = 1789392630000000000


def setup_gateway(provider="MASSIVE", *, feed=None, endpoint=None, members=None, transport=None, overrides=None, clock=None):
    members = members or ["MU"]
    defaults = {"MASSIVE": ("real_time", "BULK_SNAPSHOT"), "ALPACA": ("sip", "MULTI_SYMBOL_SNAPSHOT"),
                "FINANCIAL_DATASETS": ("corporate_historical", "COMPANY_FACTS"),
                "BIGDATA": ("research", "NEWS"), "ALPHA_VANTAGE": ("enrichment", "ENRICHMENT"),
                "YAHOO": ("screener", "SCREENER_DISCOVERY")}
    feed, endpoint = feed or defaults[provider][0], endpoint or defaults[provider][1]
    entry = {"endpoint": endpoint, "feed": feed, "mode": "FILTERED", "symbols": sorted(members),
             **dict.fromkeys(QUALIFICATIONS, "VERIFIED"), "valid_from": "2026-09-14T00:00:00+00:00",
             "expires_at": "2026-09-14T20:05:00+00:00", "maximum_requests": 3,
             "maximum_response_bytes": 1_000_000, "maximum_age_seconds": 60,
             "timeout_seconds": 20, "tier_identity": "SYNTHETIC_ACCOUNT_TIER"}
    entry.update(overrides or {})
    policy = {"mode": "OFFLINE_ONLY", "authority": locked_authority(), "providers": {provider: entry}}
    universe = {"symbols": sorted(members)}
    request = {"provider": provider, "endpoint": endpoint, "symbols": sorted(members), "feed": feed,
               "request_id": "synthetic-request-1", "mode": "FILTERED"}
    gateway = ProviderGateway(policy=policy, expected_policy=content_hash(policy), universe=universe,
                              expected_universe=content_hash(universe), transport=transport or (lambda *_a, **_k: {}),
                              clock=clock or (lambda: NOW))
    return gateway, request


def massive(symbol="MU", price=100, stamp=STAMP):
    return {"ticker": symbol, "lastQuote": {"p": price - 1, "P": price + 1, "t": stamp},
            "lastTrade": {"p": price, "t": stamp}}


def alpaca(symbol="MU", price=100, stamp=NOW):
    return {symbol: {"latestQuote": {"bp": price - 1, "ap": price + 1, "t": stamp}, "latestTrade": {"p": price, "t": stamp}}}


def collect(gateway, request):
    return gateway.collect(request, expected_request=content_hash(request))


def flow(receipts, *, stage_overrides=None, promoted=None):
    hashes = [content_hash(r) for r in receipts]
    promotion = {"status": "PROMOTED", "symbols": promoted or ["MU"], "evidence_hashes": hashes}
    stages = {stage: (lambda _obs, parent: {"status": "PASS", "parent": parent})
              for stage in ("AGENTS_MODELS", "JOHNNY_NO_SKEPTIC", "COMMITTEE", "DETERMINISTIC_RISK")}
    stages.update(stage_overrides or {})
    return governed_flow(receipts, expected_receipts=hashes, expected_parents=[r["parents"] for r in receipts],
                         promotion=promotion, expected_promotion=content_hash(promotion), stages=stages)


class GatewayTests(unittest.TestCase):
    def test_exact_517_bulk_reconciliation_and_missing(self):
        members = [f"S{i:03}" for i in range(517)]
        for count, coverage in ((517, "COMPLETE"), (516, "PARTIAL")):
            payload = {"status": "OK", "tickers": [massive(s) for s in members[:count]]}
            gateway, request = setup_gateway(members=members, transport=lambda *_a, **_k: payload)
            receipt = collect(gateway, request)
            self.assertEqual(receipt["coverage"], coverage)
            self.assertEqual(len(receipt["missing_symbols"]), 517 - count)
            self.assertFalse(receipt["atomic_exchange_snapshot"])

    def test_duplicates_unexpected_and_field_absence_retained(self):
        payload = {"tickers": [massive(), massive(), {"ticker": "OUTSIDE"}]}
        gateway, request = setup_gateway(transport=lambda *_a, **_k: payload)
        receipt = collect(gateway, request)
        self.assertEqual(receipt["duplicate_symbols"], ["MU"])
        self.assertEqual(receipt["unexpected_symbols"], ["OUTSIDE"])
        self.assertIn("OUTSIDE", receipt["field_absence"])
        self.assertEqual(receipt["coverage"], "PARTIAL")

    def test_full_market_reconciles_governed_coverage_separately(self):
        payload = {"tickers": [massive(), {"ticker": "OUTSIDE"}]}
        gateway, request = setup_gateway(overrides={"mode": "FULL_MARKET"}, transport=lambda *_a, **_k: payload)
        receipt = collect(gateway, {**request, "mode": "FULL_MARKET"})
        self.assertEqual(receipt["coverage"], "COMPLETE")
        self.assertEqual(receipt["unexpected_symbols"], ["OUTSIDE"])
        self.assertIsNone(receipt["symbols_requested"])

    def test_timeout_no_retry_and_ambiguity_reservation_survives(self):
        calls = []
        def timeout(*_a, **_k):
            calls.append(1)
            raise TimeoutError("SYNTHETIC_PRIVATE_SENTINEL")
        gateway, request = setup_gateway(transport=timeout)
        receipt = collect(gateway, request)
        self.assertEqual(len(calls), 1)
        self.assertEqual(receipt["retry_count"], 0)
        self.assertEqual(receipt["cost_credit_state"], "UNVERIFIED")
        self.assertNotIn("SYNTHETIC_PRIVATE_SENTINEL", json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            collect(gateway, request)
        self.assertEqual(len(calls), 1)

    def test_no_fourth_request(self):
        gateway, request = setup_gateway(transport=lambda *_a, **_k: {"tickers": [massive()]})
        for index in range(3):
            collect(gateway, {**request, "request_id": f"synthetic-{index}"})
        with self.assertRaisesRegex(ValueError, "BUDGET"):
            collect(gateway, {**request, "request_id": "synthetic-fourth"})

    def test_missing_each_qualification_blocks_before_transport(self):
        for field in QUALIFICATIONS:
            calls = []
            gateway, request = setup_gateway(overrides={field: "UNVERIFIED"}, transport=lambda *_a, **_k: calls.append(1))
            with self.subTest(field=field), self.assertRaises(ValueError):
                collect(gateway, request)
            self.assertEqual(calls, [])

    def test_alpaca_feeds_cannot_substitute_and_never_grant_authority(self):
        for feed, delivery in (("sip", "REAL_TIME"), ("iex", "IEX_ONLY"), ("delayed_sip", "DELAYED"), ("unavailable", "UNAVAILABLE")):
            gateway, request = setup_gateway("ALPACA", feed=feed, transport=lambda *_a, **_k: alpaca())
            receipt = collect(gateway, request)
            self.assertEqual(receipt["delay_classification"], delivery)
            self.assertTrue(all(flag is False for flag in receipt["authority"].values()))
            if feed != "sip":
                self.assertEqual(flow([receipt])["stages"][0]["status"], "BLOCKED")
        gateway, request = setup_gateway("ALPACA", transport=lambda *_a, **_k: alpaca())
        with self.assertRaises(ValueError):
            collect(gateway, {**request, "feed": "iex"})

    def test_fd_facts_do_not_prove_price_entitlement(self):
        gateway, request = setup_gateway("FINANCIAL_DATASETS")
        with self.assertRaises(ValueError):
            collect(gateway, {**request, "endpoint": "PRICE_HISTORY"})

    def test_bigdata_and_enrichment_cannot_replace_primary(self):
        for provider in ("BIGDATA", "ALPHA_VANTAGE"):
            payload = {"records": [{"ticker": "MU", "observation_time": NOW, "publication_time": NOW,
                "source_references": ["https://example.invalid/doc"], "document_identity": "synthetic-document", "indicator": "synthetic", "value": 3}]}
            gateway, request = setup_gateway(provider, transport=lambda *_a, **_k: payload)
            receipt = collect(gateway, request)
            self.assertEqual(flow([receipt])["stages"][0]["status"], "BLOCKED")
            self.assertFalse(flow([receipt])["order_submitted"])

    def test_yahoo_never_complete_universe_coverage(self):
        gateway, request = setup_gateway("YAHOO", transport=lambda *_a, **_k: {"snapshot_complete": True, "candidates": [{"ticker": "MU", "regularMarketTime": STAMP // 1_000_000_000}]})
        receipt = collect(gateway, request)
        self.assertEqual(receipt["coverage"], "DISCOVERY_ONLY")
        self.assertIsNone(receipt["symbols_requested"])
        self.assertEqual(receipt["symbols_returned"], 1)
        self.assertEqual(receipt["admissibility"], "BLOCKED")

    def test_stale_evidence_blocks_all_later_stages(self):
        gateway, request = setup_gateway("ALPACA", transport=lambda *_a, **_k: alpaca(stamp="2026-09-14T13:00:00+00:00"))
        receipt = collect(gateway, request)
        self.assertEqual(receipt["freshness"], "STALE")
        result = flow([receipt])
        self.assertEqual(result["stages"][0]["status"], "BLOCKED")
        self.assertTrue(all(r["status"] == "NOT_RUN" for r in result["stages"][1:]))

    def test_committee_pass_risk_fail_no_execution(self):
        gateway, request = setup_gateway("ALPACA", transport=lambda *_a, **_k: alpaca())
        result = flow([collect(gateway, request)], stage_overrides={"DETERMINISTIC_RISK": lambda _o, p: {"status": "FAIL", "parent": p}})
        rows = {r["stage"]: r["status"] for r in result["stages"]}
        self.assertEqual(rows["COMMITTEE"], "PASS")
        self.assertEqual(rows["DETERMINISTIC_RISK"], "FAIL")
        self.assertEqual(rows["ALPACA_PAPER_DECISION"], "NOT_RUN")
        self.assertFalse(result["order_submitted"])

    def test_agent_only_receives_promoted_symbols(self):
        seen = []
        def agents(observations, parent):
            seen.extend(r["ticker"] for r in observations)
            return {"status": "PASS", "parent": parent}
        gateway, request = setup_gateway("ALPACA", members=["MU", "SPY"], transport=lambda *_a, **_k: {**alpaca(), **alpaca("SPY")})
        result = flow([collect(gateway, request)], stage_overrides={"AGENTS_MODELS": agents})
        self.assertEqual(seen, ["MU"])
        self.assertFalse(result["order_submitted"])
        self.assertEqual(result["stages"][6]["status"], "NO_EXECUTION_OFFLINE")

    def test_disagreement_is_preserved(self):
        gateway, request = setup_gateway("ALPACA", transport=lambda *_a, **_k: alpaca())
        primary = collect(gateway, request)
        gateway, request = setup_gateway(transport=lambda *_a, **_k: {"tickers": [massive(price=200)]})
        independent = collect(gateway, request)
        result = flow([primary, independent])
        self.assertIn("MU", result["disagreements"])
        self.assertEqual(len(result["disagreements"]["MU"]), 2)

    def test_forged_provenance_blocks_before_committee(self):
        gateway, request = setup_gateway("ALPACA", transport=lambda *_a, **_k: alpaca())
        receipt = collect(gateway, request)
        receipt["provenance"] = "FORGED"
        result = flow([receipt])
        self.assertEqual(result["stages"][0]["status"], "BLOCKED")

    def test_missing_stage_and_wrong_stage_parent_fail_closed(self):
        for callback in (None, lambda _o, _p: {"status": "PASS", "parent": "wrong"}):
            gateway, request = setup_gateway("ALPACA", transport=lambda *_a, **_k: alpaca())
            result = flow([collect(gateway, request)], stage_overrides={"JOHNNY_NO_SKEPTIC": callback})
            self.assertEqual(result["stages"][4]["status"], "NOT_RUN")

    def test_receipt_determinism_and_unknown_billing_readiness(self):
        receipts = []
        for _ in range(2):
            gateway, request = setup_gateway("ALPACA", transport=lambda *_a, **_k: alpaca())
            receipts.append(collect(gateway, request))
        self.assertEqual(receipts[0], receipts[1])
        receipt = receipts[0]
        self.assertEqual(receipt["cost_credit_state"], "UNVERIFIED")
        self.assertEqual(readiness(receipt, expected=content_hash(receipt), parents=receipt["parents"])["OVERALL READINESS"], "NOT_READY")

    def test_secrets_in_response_or_exception_never_persist(self):
        for transport in (lambda *_a, **_k: {"api_key": "SYNTHETIC_PRIVATE_SENTINEL"},
                          lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("SYNTHETIC_PRIVATE_SENTINEL"))):
            stream = io.StringIO()
            gateway, request = setup_gateway(transport=transport)
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                receipt = collect(gateway, request)
            self.assertIsNone(receipt["raw_response_content_hash"])
            self.assertNotIn("SYNTHETIC_PRIVATE_SENTINEL", json.dumps(receipt) + stream.getvalue())

    def test_delay_contradiction_and_missing_time_fail_closed(self):
        for payload in ({"status": "DELAYED", "tickers": [massive()]}, {"tickers": [massive(stamp=None)]}):
            gateway, request = setup_gateway(transport=lambda *_a, **_k: payload)
            self.assertEqual(collect(gateway, request)["admissibility"], "BLOCKED")

    def test_unchanged_prices_not_stale_without_timestamp_evidence(self):
        gateway, request = setup_gateway("ALPACA", transport=lambda *_a, **_k: alpaca())
        first = collect(gateway, request)
        second = collect(gateway, {**request, "request_id": "synthetic-second"})
        self.assertEqual(first["freshness"], "CURRENT")
        self.assertEqual(second["freshness"], "CURRENT")

    def test_adapter_graph_has_no_operational_imports(self):
        root = Path(__file__).parent
        forbidden = {"socket", "requests", "httpx", "urllib.request", "subprocess", "sqlite3", "ledger", "keychain_adapter", "openai", "grok_provider", "financial_datasets"}
        for name in ("provider_gateway.py", "provider_gateway_contract.py", "provider_gateway_adapters.py", "market_baseline_plan.py", "truth_spine_contract.py"):
            tree = ast.parse((root / name).read_text())
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.add(node.module or "")
            self.assertFalse(imports & forbidden, name)

    def test_frontend_has_no_direct_provider_hosts(self):
        frontend = Path(__file__).resolve().parents[2] / "FRONT END" / "src"
        hosts = ("api.massive.com", "api.polygon.io", "data.alpaca.markets", "api.financialdatasets.ai", "alphavantage.co", "api.bigdata.com", "query1.finance.yahoo.com", "query2.finance.yahoo.com")
        for path in frontend.rglob("*"):
            if path.suffix in (".ts", ".tsx", ".js", ".jsx"):
                text = path.read_text()
                self.assertFalse(any(host in text for host in hosts), str(path.relative_to(frontend)))
