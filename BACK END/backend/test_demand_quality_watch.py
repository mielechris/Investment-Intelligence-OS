import unittest

from demand_quality_watch import assess_demand_quality


def floor():
    return {
        "lanes": {
            "supply_inventory": {
                "facts": [
                    {
                        "key": "inventory",
                        "covered": True,
                    }
                ]
            },
            "hyperscaler_demand": {
                "facts": [
                    {
                        "key": "server_activity",
                        "covered": True,
                    },
                    {
                        "key": "backlog",
                        "covered": True,
                    },
                ]
            },
        }
    }


class DemandQualityWatchTests(unittest.TestCase):

    def test_missing_channel_inventory_remains_watch(self):
        result = assess_demand_quality(
            floor(),
            direct_channel_inventory=False,
        )

        self.assertEqual(
            result["state"],
            "WATCHING",
        )

        self.assertFalse(result["covered"])

        self.assertEqual(
            result["missing_direct_fact"],
            "channel_inventory",
        )

        self.assertFalse(
            result["governance"][
                "may_authorize_trade"
            ]
        )

    def test_direct_channel_inventory_can_satisfy_analysis(self):
        result = assess_demand_quality(
            floor(),
            direct_channel_inventory=True,
        )

        self.assertEqual(
            result["state"],
            "SATISFIED",
        )

        self.assertTrue(result["covered"])

    def test_supplier_inventory_is_required(self):
        data = floor()

        data["lanes"]["supply_inventory"][
            "facts"
        ][0]["covered"] = False

        result = assess_demand_quality(
            data,
            direct_channel_inventory=True,
        )

        self.assertEqual(
            result["state"],
            "WATCHING",
        )

        self.assertFalse(result["covered"])


if __name__ == "__main__":
    unittest.main()
