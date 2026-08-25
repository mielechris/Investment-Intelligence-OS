import unittest

from evidence_gap_hunter import _qualification_assessment


def committee(disposition="WATCH"):
    agents = {
        key: {
            "disposition": "WATCH",
            "confidence": 0.85,
        }
        for key in (
            "policy",
            "macro",
            "fundamentals",
            "market_structure",
            "commodities",
            "geo_weather",
            "skeptic",
            "portfolio",
        )
    }

    return {
        "disposition": disposition,
        "confidence": 0.88,
        "required_evidence": [
            "Supplier wafer starts",
            "Hyperscaler cancellations",
        ],
        "evidence_summary": {
            "average_quality_score": 0.74,
            "evidence_count": 50,
            "critical_flags": [],
        },
        "agents": agents,
    }


def risk(
    *,
    blocking=0,
    ungoverned=0,
    include_all_watch=True,
):
    obligations = [
        {
            "lane": "supply_inventory",
            "fact_key": "wafer_starts",
        },
        {
            "lane": "hyperscaler_demand",
            "fact_key": "cancellations",
        },
    ]

    if not include_all_watch:
        obligations = obligations[:1]

    return {
        "decision": "WATCH_ONLY",
        "triggered_rules": [],
        "risk_required_evidence_mode":
            "RECONCILED_NONBLOCKING",
        "watch_obligations": obligations,
        "required_evidence_reconciliation": {
            "blocking_count": blocking,
            "watching_count": 2,
            "ungoverned_new_scope_count": ungoverned,
            "risk_can_ignore_raw_required_evidence":
                blocking == 0 and ungoverned == 0,
            "requirements": [
                {
                    "overall": "SATISFIED_WITH_WATCH",
                    "targets": [
                        {
                            "lane": "supply_inventory",
                            "fact_key": "wafer_starts",
                            "state": "WATCHING",
                        }
                    ],
                },
                {
                    "overall": "SATISFIED_WITH_WATCH",
                    "targets": [
                        {
                            "lane": "hyperscaler_demand",
                            "fact_key": "cancellations",
                            "state": "WATCHING",
                        }
                    ],
                },
            ],
        },
    }


class QualifiedBuyCandidateTests(unittest.TestCase):

    def test_governed_watch_can_qualify_without_paper_buy(self):
        legacy_matrix = [
            {
                "requirement": "old prose gap",
                "resolved": False,
            }
        ]

        result = _qualification_assessment(
            committee(),
            risk(),
            legacy_matrix,
        )

        self.assertTrue(
            result["qualified_buy_candidate"]
        )
        self.assertEqual(
            result["stage"],
            "QUALIFIED_BUY_CANDIDATE",
        )
        self.assertFalse(
            result["paper_buy_enabled"]
        )
        self.assertEqual(
            result["unmet_requirements"],
            [],
        )

    def test_real_governed_blocker_prevents_qualification(self):
        result = _qualification_assessment(
            committee(),
            risk(blocking=1),
            [],
        )

        self.assertFalse(
            result["qualified_buy_candidate"]
        )
        self.assertIn(
            "governed_blockers_clear",
            result["unmet_requirements"],
        )

    def test_ungoverned_scope_prevents_qualification(self):
        result = _qualification_assessment(
            committee(),
            risk(ungoverned=1),
            [],
        )

        self.assertFalse(
            result["qualified_buy_candidate"]
        )
        self.assertIn(
            "governed_ungoverned_scope_clear",
            result["unmet_requirements"],
        )

    def test_missing_watch_obligation_prevents_qualification(self):
        result = _qualification_assessment(
            committee(),
            risk(include_all_watch=False),
            [],
        )

        self.assertFalse(
            result["qualified_buy_candidate"]
        )
        self.assertIn(
            "governed_watch_obligations_tracked",
            result["unmet_requirements"],
        )

    def test_committee_no_trade_still_prevents_qualification(self):
        result = _qualification_assessment(
            committee(disposition="NO_TRADE"),
            risk(),
            [],
        )

        self.assertFalse(
            result["qualified_buy_candidate"]
        )
        self.assertIn(
            "committee_watch",
            result["unmet_requirements"],
        )


if __name__ == "__main__":
    unittest.main()
