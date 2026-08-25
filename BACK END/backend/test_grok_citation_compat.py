import unittest
from types import SimpleNamespace

import grok_citation_compat as compat


class FakeTimeout(Exception):
    pass


class FakeRawResponse:
    def parse(self, *, to=None):
        if to is dict:
            return {
                "citations": [
                    "https://x.com/real_one/status/1?ref=test",
                    "https://x.com/real_two/status/2",
                    "https://example.com/not-x",
                ],
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Untrusted prose https://x.com/fake/status/999",
                            }
                        ],
                    }
                ],
            }
        return SimpleNamespace(
            output_text='{"claims":[]}',
            model_dump=lambda: {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Untrusted prose https://x.com/fake/status/999",
                            }
                        ],
                    }
                ]
            },
        )


class FakeWithRaw:
    def create(self, **kwargs):
        return FakeRawResponse()


class GrokCitationCompatTests(unittest.TestCase):
    def test_untyped_raw_xai_citations_survive_sdk_model_parsing_without_trusting_prose(self):
        def normalize(value):
            text = str(value or "").split("?", 1)[0].rstrip("/")
            return text or None

        def is_x(value):
            return str(value).startswith("https://x.com/")

        def urls_from_value(value):
            if isinstance(value, str):
                return {normalize(value)} if value.startswith("http") else set()
            if isinstance(value, list):
                output = set()
                for child in value:
                    output |= urls_from_value(child)
                return output
            if isinstance(value, dict):
                output = set()
                for child in value.values():
                    output |= urls_from_value(child)
                return output
            return set()

        module = SimpleNamespace(
            _xai_citation_compat_installed=False,
            _xai_raw_x_search_installed=False,
            _extract_citation_urls=lambda response: set(),
            _urls_from_value=urls_from_value,
            _normalize_url=normalize,
            _is_x_url=is_x,
            MAX_X_SEARCH_ATTEMPTS=2,
            APITimeoutError=FakeTimeout,
            grok_model=lambda: "grok-4.6",
        )
        compat.install_grok_citation_compat(module)

        client = SimpleNamespace(
            responses=SimpleNamespace(with_raw_response=FakeWithRaw())
        )
        response, attempts = module._run_x_search(
            client,
            prompt="test",
            from_date="2026-08-22",
            to_date="2026-08-25",
        )
        citations = module._extract_citation_urls(response)

        self.assertEqual(attempts, 1)
        self.assertEqual(
            citations,
            {
                "https://x.com/real_one/status/1",
                "https://x.com/real_two/status/2",
            },
        )
        self.assertNotIn("https://x.com/fake/status/999", citations)


if __name__ == "__main__":
    unittest.main()
