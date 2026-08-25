import unittest
from unittest.mock import patch

import v1_consolidation_manifest as manifest


class V1ConsolidationManifestTests(unittest.TestCase):
    @patch.object(manifest, "production_freeze_manifest", return_value={"all_invariants_pass": True})
    @patch.object(manifest, "intelligence_safety_manifest", return_value={"intelligence_v1_frozen": True})
    def test_release_candidate_freezes_selected_v12_capabilities_only(self, intelligence, production):
        result = manifest.v1_consolidation_manifest()
        self.assertTrue(result["release_candidate_ready"])
        self.assertTrue(result["all_invariants_pass"])
        self.assertEqual(result["release_name"], "IIOS V1.0")
        self.assertEqual(result["integration_branch"], "integration/iios-v1.0")
        selected = {row["capability"] for row in result["selected_from_v1_2"]}
        self.assertEqual(selected, {"Interview-derived dynamic research agents", "SEC IPO monitoring"})
        self.assertTrue(result["legacy_v1_2_ci_defects_not_in_release_surface"])
        self.assertFalse(result["grok_included"])
        self.assertTrue(result["grok_next_batch"])
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])


if __name__ == "__main__":
    unittest.main()
