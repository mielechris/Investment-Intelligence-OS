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
    def test_compatibility_layer_does_not_replace_the_governed_request_boundary(self):
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

        original_run_x_search = module._run_x_search if hasattr(module, "_run_x_search") else None
        compat.install_grok_citation_compat(module)

        self.assertFalse(module._xai_raw_x_search_installed)
        self.assertTrue(module._xai_raw_x_search_skipped_for_cost_governor)
        self.assertIs(getattr(module, "_run_x_search", None), original_run_x_search)


if __name__ == "__main__":
    unittest.main()
