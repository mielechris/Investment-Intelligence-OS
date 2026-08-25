import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


FORM4_XML = b'''<?xml version="1.0"?>
<ownershipDocument>
  <documentType>4</documentType>
  <issuer><issuerCik>0000723125</issuerCik><issuerName>Micron Technology Inc</issuerName><issuerTradingSymbol>MU</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Example Executive</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>0</isDirector><isOfficer>1</isOfficer><officerTitle>Chief Example Officer</officerTitle><isTenPercentOwner>0</isTenPercentOwner><isOther>0</isOther></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-08-20</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode><aff10b5One>0</aff10b5One></transactionCoding>
      <transactionAmounts><transactionShares><value>1000</value></transactionShares><transactionPricePerShare><value>95.50</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>12000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-08-21</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode><aff10b5One>1</aff10b5One></transactionCoding>
      <transactionAmounts><transactionShares><value>200</value></transactionShares><transactionPricePerShare><value>100</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>11800</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-08-21</value></transactionDate>
      <transactionCoding><transactionCode>F</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>50</value></transactionShares><transactionPricePerShare><value>100</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>11750</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>'''


class InsiderIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["IIOS_DB_PATH"] = str(Path(self.tempdir.name) / "insider.db")
        for name in ("insider_intelligence", "ledger"):
            sys.modules.pop(name, None)
        import ledger

        self.ledger = importlib.reload(ledger)
        self.ledger.init_ledger()
        import insider_intelligence

        self.insider = importlib.reload(insider_intelligence)
        self.case_id = "case_insider_test"
        case = {
            "case_id": self.case_id,
            "topic": "Micron semiconductor memory thesis",
            "created_at": self.ledger.utc_now(),
            "paper_mode": True,
        }
        self.ledger.record_object(self.case_id, "case", self.case_id, case, topic=case["topic"])
        profile = {
            "monitor_profile_id": "monitor_insider_test",
            "case_id": self.case_id,
            "ticker": "MU.US",
            "direction": "LONG",
            "enabled": True,
            "created_at": self.ledger.utc_now(),
        }
        self.ledger.record_object(profile["monitor_profile_id"], "monitor_profile", self.case_id, profile, parent_id=self.case_id, topic=case["topic"])

    def tearDown(self):
        self.tempdir.cleanup()

    def test_form4_parser_separates_purchase_plan_sale_and_tax_withholding(self):
        records = self.insider.parse_form4_xml(
            FORM4_XML,
            filing_date="2026-08-22",
            accession_number="0000723125-26-000001",
            filing_url="https://www.sec.gov/example.xml",
        )
        self.assertEqual(len(records), 3)
        purchase, sale, withholding = records
        self.assertEqual(purchase["transaction_nature"], "OPEN_MARKET_PURCHASE")
        self.assertFalse(purchase["plan_10b5_1"])
        self.assertEqual(purchase["dollar_value"], 95500.0)
        self.assertEqual(sale["transaction_nature"], "OPEN_MARKET_SALE")
        self.assertTrue(sale["plan_10b5_1"])
        self.assertEqual(withholding["transaction_nature"], "TAX_WITHHOLDING_OR_PAYMENT")
        self.assertEqual(purchase["reporting_owner_role"], "Chief Example Officer")

    def test_classification_does_not_call_grants_or_exercises_open_market(self):
        self.assertEqual(self.insider.classify_transaction("A", "A"), "EQUITY_AWARD_OR_ISSUER_TRANSFER")
        self.assertEqual(self.insider.classify_transaction("M", "A"), "OPTION_EXERCISE_OR_CONVERSION")
        self.assertEqual(self.insider.classify_transaction("F", "D"), "TAX_WITHHOLDING_OR_PAYMENT")
        self.assertEqual(self.insider.classify_transaction("G", "D"), "GIFT")

    def test_persisted_public_records_become_contextual_evidence(self):
        records = self.insider.parse_form4_xml(
            FORM4_XML,
            filing_date="2026-08-22",
            accession_number="0000723125-26-000001",
            filing_url="https://www.sec.gov/example.xml",
        )
        added = self.insider.persist_insider_records(self.case_id, records)
        self.assertEqual(len(added), 3)
        evidence = self.insider.insider_evidence(self.case_id)
        self.assertEqual(len(evidence), 3)
        self.assertTrue(all(item["source_type"] == "filing" for item in evidence))
        self.assertTrue(all(item["insider_context_only"] for item in evidence))
        status = self.insider.insider_status(self.case_id)
        self.assertEqual(status["summary"]["open_market_buys"], 1)
        self.assertEqual(status["summary"]["open_market_sales"], 1)
        self.assertEqual(status["summary"]["planned_10b5_1_sales"], 1)


if __name__ == "__main__":
    unittest.main()
