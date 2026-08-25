import unittest
from unittest.mock import patch

import official_sources


class OfficialSourceTests(unittest.TestCase):
    @patch.object(official_sources, "_request_bytes")
    def test_official_web_extracts_keyword_windows(self, mock_request):
        mock_request.return_value = b"""
        <html><body>
        <h1>Micron Investor Relations</h1>
        <p>Micron reported record fiscal Q3 revenue and strong AI memory demand.</p>
        <p>HBM capacity is expanding and strategic customer agreements improve visibility.</p>
        <p>The company is investing at record levels in technology, products and supply.</p>
        </body></html>
        """
        items = official_sources.fetch_official_web(
            {
                "url": "https://investors.micron.com/overview/default.aspx",
                "label": "Micron Investor Relations",
                "keywords": ["record fiscal Q3", "HBM", "investing at record levels"],
                "limit": 3,
            }
        )
        self.assertGreaterEqual(len(items), 1)
        self.assertTrue(all(item["source_type"] == "company" for item in items))
        self.assertTrue(all(item["reliability_score"] == 0.93 for item in items))
        self.assertTrue(any("HBM" in item["claim"] for item in items))

    @patch.object(official_sources, "_request_bytes")
    def test_google_news_rss_normalizes_items(self, mock_request):
        mock_request.return_value = b"""<?xml version='1.0' encoding='UTF-8'?>
        <rss><channel>
          <item>
            <title>Micron memory demand strengthens</title>
            <link>https://example.com/micron</link>
            <pubDate>Sat, 22 Aug 2026 15:00:00 GMT</pubDate>
            <source>Example News</source>
          </item>
        </channel></rss>"""
        items = official_sources.fetch_google_news_rss({"query": "Micron HBM", "limit": 5})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "Example News")
        self.assertEqual(items[0]["evidence_type"], "news")
        self.assertIn("2026-08-22", items[0]["timestamp"])


if __name__ == "__main__":
    unittest.main()
