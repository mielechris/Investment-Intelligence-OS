import unittest
from unittest.mock import patch

import grok_discovery_lead_time as lead


class GrokDiscoveryLeadTimeTests(unittest.TestCase):
    @patch.object(lead, "_rows")
    def test_forward_pair_is_marked_prospective(self, rows):
        rows.side_effect = lambda object_type: [
            {
                "source": "GROK_X",
                "ticker": "ABC",
                "observed_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "source": "IIOS_NATIVE",
                "ticker": "ABC",
                "observed_at": "2026-01-01T00:10:00+00:00",
            },
        ] if object_type == "grok_value_discovery_observation" else []
        report = lead.build_discovery_lead_time_report()
        self.assertEqual(report["measurable_pair_count"], 1)
        self.assertEqual(report["prospective_pair_count"], 1)
        self.assertEqual(report["grok_earlier_count"], 1)
        self.assertEqual(report["prospective_grok_earlier_count"], 1)
        self.assertEqual(report["median_grok_lead_minutes"], 10.0)
        self.assertEqual(report["prospective_median_grok_lead_minutes"], 10.0)
        self.assertTrue(report["rows"][0]["prospective_pair"])
        self.assertFalse(report["trade_execution_permission"])
        self.assertFalse(report["live_execution"])

    @patch.object(lead, "_rows")
    def test_legacy_first_seen_does_not_mask_new_prospective_pair(self, rows):
        def fake_rows(object_type):
            if object_type == "grok_value_discovery_observation":
                return [
                    {
                        "source": "GROK_X",
                        "ticker": "ABC",
                        "observed_at": "2026-02-01T10:00:00+00:00",
                    },
                    {
                        "source": "IIOS_NATIVE",
                        "ticker": "ABC",
                        "observed_at": "2026-02-01T10:30:00+00:00",
                    },
                ]
            if object_type == "grok_opportunity_candidate":
                return [{
                    "ticker": "ABC",
                    "created_at": "2026-01-01T09:00:00+00:00",
                    "eligible_for_iios_revalidation": True,
                }]
            if object_type == "opportunity_candidate":
                return [{
                    "ticker": "ABC",
                    "created_at": "2026-01-01T08:00:00+00:00",
                }]
            return []

        rows.side_effect = fake_rows
        report = lead.build_discovery_lead_time_report()
        row = report["rows"][0]
        self.assertEqual(report["prospective_pair_count"], 1)
        self.assertEqual(report["prospective_grok_earlier_count"], 1)
        self.assertEqual(report["prospective_median_grok_lead_minutes"], 30.0)
        self.assertEqual(row["prospective_grok_lead_minutes"], 30.0)
        self.assertEqual(row["prospective_winner"], "GROK_EARLIER")
        self.assertEqual(row["grok_measurement_mode"], "LEGACY_LEDGER_FALLBACK")
        self.assertEqual(row["iios_measurement_mode"], "LEGACY_LEDGER_FALLBACK")


if __name__ == "__main__":
    unittest.main()
