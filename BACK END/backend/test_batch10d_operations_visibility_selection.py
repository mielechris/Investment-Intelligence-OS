import unittest

import operations_visibility as visibility


class Batch10DOperationsVisibilitySelectionTests(unittest.TestCase):
    def test_active_deep_watch_case_beats_newer_dormant_duplicate(self):
        rows = [
            {
                "case_id": "case_mu_newer_dormant",
                "ticker": "MU",
                "dead_end": True,
                "monitoring_active": False,
                "valid_no_capital_outcome": False,
                "qualified_buy_candidate": False,
                "paper_execution_complete": False,
                "deep_watch": {"obligation_count": 0, "material_change_count": 0},
                "options_shadow": {"observation_count": 0},
            },
            {
                "case_id": "case_mu_active",
                "ticker": "MU",
                "dead_end": False,
                "monitoring_active": True,
                "valid_no_capital_outcome": True,
                "qualified_buy_candidate": False,
                "paper_execution_complete": False,
                "deep_watch": {"obligation_count": 8, "material_change_count": 0},
                "options_shadow": {"observation_count": 0},
            },
        ]

        selected, legacy_gap_count = visibility._select_current_cases(rows, 25)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["case_id"], "case_mu_active")
        self.assertEqual(legacy_gap_count, 1)

    def test_duplicate_legacy_tickers_do_not_flood_live_rows(self):
        rows = [
            {
                "case_id": "case_hrl_1",
                "ticker": "HRL",
                "dead_end": True,
                "monitoring_active": False,
                "valid_no_capital_outcome": False,
                "qualified_buy_candidate": False,
                "paper_execution_complete": False,
                "deep_watch": {"obligation_count": 0, "material_change_count": 0},
                "options_shadow": {"observation_count": 0},
            },
            {
                "case_id": "case_hrl_2",
                "ticker": "HRL",
                "dead_end": True,
                "monitoring_active": False,
                "valid_no_capital_outcome": False,
                "qualified_buy_candidate": False,
                "paper_execution_complete": False,
                "deep_watch": {"obligation_count": 0, "material_change_count": 0},
                "options_shadow": {"observation_count": 0},
            },
            {
                "case_id": "case_mstr_1",
                "ticker": "MSTR",
                "dead_end": True,
                "monitoring_active": False,
                "valid_no_capital_outcome": False,
                "qualified_buy_candidate": False,
                "paper_execution_complete": False,
                "deep_watch": {"obligation_count": 0, "material_change_count": 0},
                "options_shadow": {"observation_count": 0},
            },
        ]

        selected, legacy_gap_count = visibility._select_current_cases(rows, 25)

        self.assertEqual(selected, [])
        self.assertEqual(legacy_gap_count, 3)

    def test_options_shadow_requires_actual_observation_to_make_case_operational(self):
        no_observation = {
            "dead_end": False,
            "monitoring_active": False,
            "valid_no_capital_outcome": False,
            "qualified_buy_candidate": False,
            "paper_execution_complete": False,
            "deep_watch": {"obligation_count": 0, "material_change_count": 0},
            "options_shadow": {"mode": "SHADOW_OBSERVATION_ONLY", "observation_count": 0},
        }
        observed = {
            **no_observation,
            "options_shadow": {"mode": "SHADOW_OBSERVATION_ONLY", "observation_count": 2},
        }

        self.assertFalse(visibility._is_current_operational_case(no_observation))
        self.assertTrue(visibility._is_current_operational_case(observed))


if __name__ == "__main__":
    unittest.main()
