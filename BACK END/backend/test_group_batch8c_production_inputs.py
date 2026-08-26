import os
import unittest
from unittest.mock import patch

import cme_fedwatch_adapter as fedwatch
import production_index_universe as universe


class GroupBatch8CProductionInputsTests(unittest.TestCase):
    def test_html_symbol_parser(self):
        html = "<table>" + "".join(
            f"<tr><td>SYM{i}</td><td>Company {i}</td></tr>"
            for i in range(100)
        ) + "</table>"
        symbols = universe.parse_html_symbols(html)
        self.assertEqual(len(symbols), 100)
        self.assertEqual(symbols[0], "SYM0")

    def test_csv_symbol_parser(self):
        text = "Symbol,Company\nAAPL,Apple\nMSFT,Microsoft\nBRK.B,Berkshire\n"
        self.assertEqual(
            universe.parse_delimited_symbols(text),
            ["AAPL", "MSFT", "BRK.B"],
        )

    def test_json_symbol_parser(self):
        payload = {
            "data": [
                {"symbol": "nvda"},
                {"ticker": "MSFT.US"},
                {"Symbol": "GOOGL"},
            ]
        }
        self.assertEqual(
            universe.parse_json_symbols(payload),
            ["NVDA", "MSFT", "GOOGL"],
        )

    def test_index_count_validation_fails_closed(self):
        ok, error = universe.validate_index_count("SP500", ["AAPL"] * 10)
        self.assertFalse(ok)
        self.assertIn("Incomplete", error)

    def test_full_refresh_requires_both_indexes(self):
        sp = [f"S{i}" for i in range(500)]
        ndx = [f"N{i}" for i in range(100)]

        def fake_read(spec):
            symbols = sp if spec.index_key == "SP500" else ndx
            return {
                "source_mode": "OFFICIAL_WEB_SOURCE",
                "source_ref": f"https://example.test/{spec.index_key}",
                "symbols": symbols,
            }

        with patch.object(universe, "_read_source", side_effect=fake_read):
            result = universe.refresh_official_index_universe()

        self.assertEqual(result["status"], "CAPTURED")
        self.assertTrue(result["verified_complete"])
        self.assertEqual(result["symbol_count"], 600)
        self.assertTrue(result["strict_membership"])
        self.assertFalse(result["live_execution"])

    def test_partial_refresh_returns_no_universe(self):
        sp = [f"S{i}" for i in range(500)]

        def fake_read(spec):
            return {
                "source_mode": "OFFICIAL_WEB_SOURCE",
                "source_ref": f"https://example.test/{spec.index_key}",
                "symbols": sp if spec.index_key == "SP500" else ["NVDA"],
            }

        with patch.object(universe, "_read_source", side_effect=fake_read):
            result = universe.refresh_official_index_universe()

        self.assertEqual(result["status"], "SOURCE_INCOMPLETE")
        self.assertFalse(result["verified_complete"])
        self.assertEqual(result["symbols"], [])
        self.assertEqual(result["symbol_count"], 0)

    def test_fedwatch_mapping_normalizes_percentages(self):
        result = fedwatch.normalize_fedwatch_payload(
            {
                "probabilities": {
                    "Cut 25 bps": 63,
                    "Hold": 31,
                    "Hike 25 bps": 6,
                }
            }
        )
        probs = result["probabilities"]
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=7)
        self.assertAlmostEqual(probs["CUT_25"], 0.63, places=7)
        self.assertAlmostEqual(probs["HOLD"], 0.31, places=7)
        self.assertFalse(result["probabilities_invented"])

    def test_fedwatch_nested_rows(self):
        result = fedwatch.normalize_fedwatch_payload(
            {
                "data": [
                    {
                        "outcomes": [
                            {"scenario": "CUT_50", "probability": 0.15},
                            {"scenario": "CUT_25", "probability": 0.55},
                            {"scenario": "HOLD", "probability": 0.30},
                        ]
                    }
                ]
            }
        )
        self.assertEqual(set(result["probabilities"]), {"CUT_50", "CUT_25", "HOLD"})
        self.assertAlmostEqual(sum(result["probabilities"].values()), 1.0, places=7)

    def test_ambiguous_fedwatch_payload_fails_closed(self):
        with self.assertRaises(ValueError):
            fedwatch.normalize_fedwatch_payload(
                {
                    "targetRanges": [
                        {"lower": 4.75, "upper": 5.0, "probability": 70},
                        {"lower": 5.0, "upper": 5.25, "probability": 30},
                    ]
                }
            )

    def test_fedwatch_status_never_exposes_secret(self):
        with patch.dict(
            os.environ,
            {
                "IIOS_CME_FEDWATCH_URL": "https://dataservices.cmegroup.com/fedwatch",
                "IIOS_CME_FEDWATCH_API_KEY": "super-secret-value",
                "IIOS_CME_FEDWATCH_MODE": "REALTIME",
            },
            clear=False,
        ):
            status = fedwatch.configuration_status()
            rendered = repr(status)
        self.assertTrue(status["credential_present"])
        self.assertFalse(status["credential_exposed"])
        self.assertNotIn("super-secret-value", rendered)
        self.assertEqual(status["mode"], "REALTIME")


if __name__ == "__main__":
    unittest.main()
