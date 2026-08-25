import unittest

from open_evidence_watch import candidate_qualifies


class OpenEvidenceWatchTests(unittest.TestCase):
    def test_quantified_wafer_starts_candidate_qualifies(self):
        self.assertTrue(
            candidate_qualifies(
                "wafer_starts",
                "The fab reached 120,000 wafer starts per month.",
            )
        )

    def test_unquantified_wafer_capacity_does_not_qualify(self):
        self.assertFalse(
            candidate_qualifies(
                "wafer_starts",
                "The company plans additional wafer capacity.",
            )
        )

    def test_quantified_data_center_cancellation_qualifies(self):
        self.assertTrue(
            candidate_qualifies(
                "cancellations",
                "The company canceled 200 MW of planned AI data-center capacity.",
            )
        )

    def test_generic_cancellation_does_not_qualify(self):
        self.assertFalse(
            candidate_qualifies(
                "cancellations",
                "The company canceled an unrelated marketing event.",
            )
        )


if __name__ == "__main__":
    unittest.main()
