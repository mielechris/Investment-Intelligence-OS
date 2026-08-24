import unittest

from hyperscaler_contract_context import CONTRACT_CONTEXT
from primary_evidence_contracts import fact_matches


class HyperscalerContractContextTests(unittest.TestCase):
    def test_supplier_side_context_is_not_hyperscaler_memory_terms_fact(self):
        memory_terms_fact = {
            "key": "memory_terms",
            "terms": ("memory content", "customer agreement", "strategic agreement", "enforceable"),
        }
        context_record = {
            "primary_fact_key": "memory_terms_context",
            "claim": CONTRACT_CONTEXT[0]["claim"],
            "source": CONTRACT_CONTEXT[0]["source"],
            "url": CONTRACT_CONTEXT[0]["url"],
        }
        self.assertFalse(fact_matches(context_record, memory_terms_fact))

    def test_context_contains_binding_volume_and_hbm_scope(self):
        claims = " ".join(str(row["claim"]) for row in CONTRACT_CONTEXT).lower()
        self.assertIn("take-or-pay", claims)
        self.assertIn("binding commitments", claims)
        self.assertIn("hbm", claims)
        self.assertIn("$100 billion", claims)


if __name__ == "__main__":
    unittest.main()
