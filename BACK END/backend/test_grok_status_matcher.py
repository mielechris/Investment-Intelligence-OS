import unittest
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit

import grok_status_matcher as matcher


class GrokStatusMatcherTests(unittest.TestCase):
    def _module(self):
        def normalize(value):
            text = str(value or "").strip()
            if not text.startswith(("https://", "http://")):
                return None
            parts = urlsplit(text)
            return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", "", ""))

        def is_x(value):
            return urlsplit(value).netloc.lower() in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}

        def original_filter(raw_claims, citation_urls):
            admitted = []
            quarantined = []
            for index, raw in enumerate(raw_claims):
                verified = []
                for value in raw.get("source_urls") or []:
                    normalized = normalize(value)
                    if normalized in citation_urls and normalized not in verified:
                        verified.append(normalized)
                reasons = []
                if not verified:
                    reasons.append("NO_VERIFIED_X_CITATION")
                elif len(verified) < 2:
                    reasons.append("SINGLE_SOURCE_SOCIAL_CLAIM")
                item = {
                    "grok_context_item_id": f"grok_context_{index+1}",
                    "source_urls": verified,
                    "source_count": len(verified),
                    "context_admitted": not reasons,
                    "quarantine_reasons": reasons,
                }
                (quarantined if reasons else admitted).append(item)
            return {
                "admitted": admitted,
                "quarantined": quarantined,
                "admitted_count": len(admitted),
                "quarantined_count": len(quarantined),
            }

        return SimpleNamespace(
            _grok_status_matcher_installed=False,
            _normalize_url=normalize,
            _is_x_url=is_x,
            MIN_ADMITTED_SOURCES=2,
            filter_grok_claims=original_filter,
        )

    def test_account_urls_match_xai_i_status_citations_by_numeric_id(self):
        module = self._module()
        matcher.install_grok_status_matcher(module)
        result = module.filter_grok_claims(
            [{
                "source_urls": [
                    "https://x.com/alpha/status/2091042867053494670?ref=test",
                    "https://x.com/beta/status/2091096949474853016",
                ]
            }],
            {
                "https://x.com/i/status/2091042867053494670",
                "https://x.com/i/status/2091096949474853016",
            },
        )
        self.assertEqual(result["admitted_count"], 1)
        self.assertEqual(result["admitted"][0]["source_count"], 2)
        self.assertEqual(result["admitted"][0]["independent_account_count"], 2)

    def test_two_posts_from_same_account_do_not_satisfy_independence(self):
        module = self._module()
        matcher.install_grok_status_matcher(module)
        result = module.filter_grok_claims(
            [{
                "source_urls": [
                    "https://x.com/alpha/status/111",
                    "https://x.com/alpha/status/222",
                ]
            }],
            {
                "https://x.com/i/status/111",
                "https://x.com/i/status/222",
            },
        )
        self.assertEqual(result["admitted_count"], 0)
        self.assertEqual(result["quarantined_count"], 1)
        self.assertIn("INSUFFICIENT_INDEPENDENT_X_ACCOUNTS", result["quarantined"][0]["quarantine_reasons"])

    def test_unrelated_status_id_remains_unverified(self):
        module = self._module()
        matcher.install_grok_status_matcher(module)
        result = module.filter_grok_claims(
            [{"source_urls": ["https://x.com/alpha/status/333"]}],
            {"https://x.com/i/status/444"},
        )
        self.assertEqual(result["admitted_count"], 0)
        self.assertIn("NO_VERIFIED_X_CITATION", result["quarantined"][0]["quarantine_reasons"])


if __name__ == "__main__":
    unittest.main()
