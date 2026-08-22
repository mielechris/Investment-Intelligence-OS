import json
import unittest
from unittest.mock import patch

import source_ingestion


class SourceIngestionTests(unittest.TestCase):
    def test_registry_contains_no_key_sources(self):
        self.assertIn("sec_companyfacts", source_ingestion.SOURCE_REGISTRY)
        self.assertIn("noaa_alerts", source_ingestion.SOURCE_REGISTRY)
        self.assertIn("gdelt_news", source_ingestion.SOURCE_REGISTRY)
        self.assertIn("fred_series", source_ingestion.SOURCE_REGISTRY)
        self.assertTrue(all(not item["requires_key"] for item in source_ingestion.SOURCE_REGISTRY.values()))

    @patch.object(source_ingestion, "_json_request")
    def test_noaa_alert_normalizes_to_raw_evidence(self, mock_json):
        mock_json.return_value = {
            "features": [
                {
                    "id": "alert-1",
                    "properties": {
                        "event": "Hurricane Warning",
                        "headline": "Hurricane warning for test area",
                        "description": "Strong hurricane conditions expected.",
                        "sent": "2026-08-22T16:00:00+00:00",
                        "severity": "Extreme",
                        "certainty": "Observed",
                        "urgency": "Immediate",
                        "areaDesc": "Test County",
                    },
                }
            ]
        }
        items = source_ingestion.fetch_noaa_alerts({"area": "FL"})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source_type"], "official")
        self.assertEqual(items[0]["evidence_type"], "weather")
        self.assertIn("Hurricane", items[0]["title"])

    @patch.object(source_ingestion, "_json_request")
    def test_gdelt_articles_become_news_evidence(self, mock_json):
        mock_json.return_value = {
            "articles": [
                {
                    "url": "https://example.com/story",
                    "title": "Semiconductor policy update",
                    "domain": "example.com",
                    "seendate": "20260822T160000Z",
                    "language": "English",
                    "sourcecountry": "United States",
                }
            ]
        }
        items = source_ingestion.fetch_gdelt_news({"query": "semiconductor", "limit": 5})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["evidence_type"], "news")
        self.assertEqual(items[0]["claim"], "Semiconductor policy update")

    @patch.object(source_ingestion, "_request")
    def test_fred_csv_becomes_macro_evidence(self, mock_request):
        mock_request.return_value = b"observation_date,DFF\n2026-08-20,5.25\n2026-08-21,5.25\n"
        items = source_ingestion.fetch_fred_series({"series_id": "DFF", "limit": 2})
        self.assertEqual(len(items), 2)
        self.assertEqual(items[-1]["claim"], "DFF=5.25")
        self.assertEqual(items[-1]["evidence_type"], "macro")

    @patch.object(source_ingestion, "_json_request")
    def test_sec_companyfacts_extracts_selected_fact(self, mock_json):
        mock_json.return_value = {
            "entityName": "Test Corp",
            "facts": {
                "us-gaap": {
                    "Assets": {
                        "units": {
                            "USD": [
                                {
                                    "val": 1000000,
                                    "end": "2026-06-30",
                                    "filed": "2026-08-01",
                                    "form": "10-Q",
                                    "accn": "000000-26-000001",
                                }
                            ]
                        }
                    }
                }
            },
        }
        items = source_ingestion.fetch_sec_companyfacts({"cik": "320193", "tags": ["Assets"], "limit": 5})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Test Corp Assets")
        self.assertEqual(items[0]["value"], 1000000)

    def test_ingest_sources_is_fail_soft(self):
        def ok_fetcher(params):
            return [{"source": "fixture", "claim": "ok"}]

        with patch.dict(source_ingestion.FETCHERS, {"fixture": ok_fetcher}, clear=False):
            result = source_ingestion.ingest_sources(
                [
                    {"source": "fixture", "params": {}},
                    {"source": "does_not_exist", "params": {}},
                ]
            )
        self.assertEqual(result["successful_sources"], 1)
        self.assertEqual(result["failed_sources"], 1)
        self.assertEqual(len(result["evidence_items"]), 1)


if __name__ == "__main__":
    unittest.main()
