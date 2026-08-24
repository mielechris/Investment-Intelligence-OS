import unittest

from analyst_consensus_fallback import install_analyst_consensus_fallback, parse_stockanalysis_consensus


class AnalystConsensusParserTests(unittest.TestCase):
    def test_parser_extracts_only_forecast_averages(self):
        html = """
        <html><body>
          <h2>Revenue Forecast</h2>
          <table>
            <tr><th>Revenue</th><th>2026</th><th>2027</th></tr>
            <tr><td>High</td><td>138.8B</td><td>200B</td></tr>
            <tr><td>Avg</td><td>129.7B</td><td>190B</td></tr>
            <tr><td>Low</td><td>122.6B</td><td>180B</td></tr>
          </table>
          <h2>Revenue Growth</h2>
          <h2>EPS Forecast</h2>
          <table>
            <tr><th>EPS</th><th>2026</th><th>2027</th></tr>
            <tr><td>High</td><td>80.16</td><td>160.00</td></tr>
            <tr><td>Avg</td><td>73.36</td><td>150.00</td></tr>
            <tr><td>Low</td><td>67.39</td><td>140.00</td></tr>
          </table>
          <h2>EPS Growth</h2>
          <p>Price Target $1501.98</p>
          <p>Data Sources: S&amp;P Global Market Intelligence and TipRanks</p>
          <p>Last updated: Aug 20, 2026</p>
        </body></html>
        """
        parsed = parse_stockanalysis_consensus(html, current_year=2026)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["revenue_consensus"], 129_700_000_000.0)
        self.assertEqual(parsed["eps_consensus"], 73.36)
        self.assertEqual(parsed["updated_at"], "2026-08-20T00:00:00+00:00")
        self.assertIn("S&P Global", parsed["attribution"])

    def test_parser_rejects_page_without_forecast_average(self):
        html = "<html><body><h2>Analyst Rating</h2><p>Price Target $1500</p></body></html>"
        self.assertIsNone(parse_stockanalysis_consensus(html, current_year=2026))


class _FakeModule:
    def __init__(self):
        self.saved = {}
        self.events = []
        self._capture_market = lambda case_id, case: ([], [])
        self._lane_status = lambda case_id, lane, records: {"facts": [], "note": ""}
        self._persist_record = self._base_persist

    def _base_persist(self, case_id, case, lane, fact_key, item):
        record_id = f"record_{len(self.saved) + 1}"
        record = {
            "primary_evidence_id": record_id,
            "lane": lane,
            "fact_key": fact_key,
            "source_type": item.get("source_type"),
            "source_grade": "CONTEXT",
            "gap_resolution_eligible": False,
            "trade_execution_permission": False,
        }
        self.saved[record_id] = record
        return record

    def record_object(self, record_id, object_type, case_id, payload, **kwargs):
        self.saved[record_id] = payload

    def record_event(self, case_id, event_type, **kwargs):
        self.events.append((event_type, kwargs))

    def list_objects(self, case_id, object_type):
        return list(self.saved.values())

    def latest_object(self, object_type, case_id=None):
        return {"ticker": "MU.US"} if object_type == "monitor_profile" else None

    @staticmethod
    def utc_now():
        return "2026-08-23T20:54:00-07:00"


class AnalystConsensusScopeTests(unittest.TestCase):
    def test_consensus_source_class_is_fact_scoped(self):
        module = _FakeModule()
        install_analyst_consensus_fallback(module)

        consensus = module._persist_record(
            "case_1",
            {"topic": "test"},
            "valuation_market",
            "consensus",
            {"source_type": "consensus_data"},
        )
        self.assertEqual(consensus["source_grade"], "GOVERNED_CONSENSUS")
        self.assertTrue(consensus["gap_resolution_eligible"])
        self.assertFalse(consensus["trade_execution_permission"])

        short = module._persist_record(
            "case_1",
            {"topic": "test"},
            "valuation_market",
            "short_interest",
            {"source_type": "consensus_data"},
        )
        self.assertEqual(short["source_grade"], "CONTEXT")
        self.assertFalse(short["gap_resolution_eligible"])


if __name__ == "__main__":
    unittest.main()
