import unittest

import insider_ir_fallback as fallback


SAMPLE = b"""
<table>
<tr><th>Filing date</th><th>Form</th><th>Description</th><th>Filer</th><th>View</th></tr>
<tr><td>Jul 28, 2026</td><td>4</td><td>Statement of changes in beneficial ownership of securities</td><td>MEHROTRA SANJAY</td><td><a href=\"https://example.com/0001242654-26-000014.pdf\">View HTML</a></td></tr>
<tr><td>Jul 24, 2026</td><td>144</td><td>Filed by insiders prior intended sale of restricted stock.</td><td></td><td><a href=\"https://example.com/0001969223-26-000797.pdf\">View HTML</a></td></tr>
<tr><td>Feb 13, 2026</td><td>SCHEDULE 13G/A</td><td>SCHEDULE 13G/A - Description</td><td></td><td><a href=\"https://example.com/0001422849-26-000035.pdf\">View HTML</a></td></tr>
</table>
"""


class InsiderIRFallbackTests(unittest.TestCase):
    def test_form4_is_context_only_without_transaction_detail(self):
        records = fallback.parse_micron_ir_filings(SAMPLE.decode(), ticker="MU")
        form4 = next(item for item in records if item["form"] == "4")
        self.assertEqual(form4["record_kind"], "FORM4_FILING_METADATA")
        self.assertEqual(form4["reporting_owner"], "MEHROTRA SANJAY")
        self.assertEqual(form4["transaction_nature"], "FORM4_TRANSACTION_DETAIL_UNAVAILABLE")
        self.assertEqual(form4["admission_status"], "CONTEXT_ONLY")
        self.assertFalse(form4["transaction_detail_complete"])

    def test_form144_is_not_treated_as_completed_sale(self):
        records = fallback.parse_micron_ir_filings(SAMPLE.decode(), ticker="MU")
        notice = next(item for item in records if item["form"] == "144")
        self.assertEqual(notice["record_kind"], "FORM144_NOTICE")
        self.assertEqual(notice["transaction_nature"], "NOTICE_OF_PROPOSED_SALE")
        self.assertEqual(notice["admission_status"], "CONTEXT_ONLY")

    def test_13g_filing_presence_is_admitted_ownership_context(self):
        records = fallback.parse_micron_ir_filings(SAMPLE.decode(), ticker="MU")
        ownership = next(item for item in records if item["form"] == "SCHEDULE 13G/A")
        self.assertEqual(ownership["record_kind"], "BENEFICIAL_OWNERSHIP_FILING")
        self.assertEqual(ownership["admission_status"], "ADMITTED")
        self.assertTrue(ownership["fallback_source"])


if __name__ == "__main__":
    unittest.main()
