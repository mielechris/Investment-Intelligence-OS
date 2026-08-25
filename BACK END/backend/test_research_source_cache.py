import unittest
from types import SimpleNamespace

import research_source_cache as cache


class ResearchSourceCacheTests(unittest.TestCase):
    def setUp(self):
        cache.clear_research_source_cache()

    def _module(self):
        calls = []

        def ingest_sources(requests):
            calls.append(requests)
            request = requests[0]
            source_key = request.get("source")
            params = request.get("params") or {}
            if source_key == "broken":
                return {
                    "source_results": [{
                        "source_key": source_key,
                        "status": "error",
                        "fetched_at": "now",
                        "items": [],
                        "error": "boom",
                    }]
                }
            return {
                "source_results": [{
                    "source_key": source_key,
                    "status": "ok",
                    "fetched_at": "now",
                    "items": [{"source": source_key, "claim": str(params)}],
                    "error": None,
                }]
            }

        module = SimpleNamespace(
            _research_source_cache_installed=False,
            ingest_sources=ingest_sources,
            utc_now=lambda: "2026-08-24T21:30:00+00:00",
        )
        return module, calls

    def test_exact_successful_request_is_reused(self):
        module, calls = self._module()
        cache.install_research_source_cache(module)
        request = [{"source": "fred_series", "params": {"series_id": "DFF"}}]

        first = module.ingest_sources(request)
        second = module.ingest_sources(request)

        self.assertEqual(len(calls), 1)
        self.assertEqual(first["cache_hits"], 0)
        self.assertEqual(second["cache_hits"], 1)
        self.assertFalse(first["source_results"][0]["cache_hit"])
        self.assertTrue(second["source_results"][0]["cache_hit"])
        self.assertFalse(second["judgment_output_cache"])
        self.assertFalse(second["trade_execution_permission"])
        self.assertFalse(second["live_execution"])

    def test_changed_params_do_not_reuse_cache(self):
        module, calls = self._module()
        cache.install_research_source_cache(module)
        module.ingest_sources([{"source": "gdelt_news", "params": {"query": "MU"}}])
        module.ingest_sources([{"source": "gdelt_news", "params": {"query": "NVDA"}}])
        self.assertEqual(len(calls), 2)

    def test_failed_requests_are_never_cached(self):
        module, calls = self._module()
        cache.SOURCE_TTL_SECONDS["broken"] = 60
        try:
            cache.install_research_source_cache(module)
            request = [{"source": "broken", "params": {}}]
            module.ingest_sources(request)
            module.ingest_sources(request)
            self.assertEqual(len(calls), 2)
        finally:
            cache.SOURCE_TTL_SECONDS.pop("broken", None)

    def test_market_quotes_are_not_added_to_source_cache(self):
        self.assertNotIn("market_quote", cache.SOURCE_TTL_SECONDS)
        self.assertNotIn("cnbc_quote", cache.SOURCE_TTL_SECONDS)
        self.assertNotIn("yahoo_quote", cache.SOURCE_TTL_SECONDS)

    def test_plan_is_read_only_and_paper_only(self):
        paths = {route.path.lower() for route in cache.router.routes}
        self.assertEqual(paths, {"/research-source-cache/plan"})
        plan = cache.research_source_cache_plan()
        self.assertTrue(plan["exact_request_match_required"])
        self.assertTrue(plan["cache_successes_only"])
        self.assertFalse(plan["judgment_output_cache"])
        self.assertFalse(plan["auto_trade_authority"])
        self.assertFalse(plan["paper_order_permission"])
        self.assertFalse(plan["trade_execution_permission"])
        self.assertFalse(plan["live_execution"])


if __name__ == "__main__":
    unittest.main()
