import unittest
from types import SimpleNamespace
from unittest.mock import patch

import grok_xai_sdk_adapter as adapter


class FakeUsage:
    cost_in_usd_ticks = 123456789


class FakeResponse:
    content = '{"summary":"ok","claims":[]}'
    citations = [
        "https://x.com/alpha/status/1",
        "https://x.com/beta/status/2",
    ]
    usage = FakeUsage()
    server_side_tool_usage = {"SERVER_SIDE_TOOL_X_SEARCH": 3}


class GrokXaiSdkAdapterTests(unittest.TestCase):
    def test_response_adapter_preserves_citations_usage_and_content(self):
        wrapped = adapter._XaiSdkResponseAdapter(FakeResponse())
        self.assertEqual(wrapped.output_text, FakeResponse.content)
        self.assertEqual(wrapped.citations, FakeResponse.citations)
        dumped = wrapped.model_dump()
        self.assertEqual(dumped["citations"], FakeResponse.citations)
        self.assertEqual(dumped["usage"]["cost_in_usd_ticks"], 123456789)
        self.assertEqual(dumped["usage"]["num_server_side_tools_used"], 3)

    def test_installer_routes_only_x_search_transport(self):
        module = SimpleNamespace(
            _xai_official_sdk_adapter_installed=False,
            MAX_X_SEARCH_ATTEMPTS=2,
        )
        adapter.install_xai_sdk_x_search(module)
        self.assertTrue(module._xai_official_sdk_adapter_installed)

        with patch.object(adapter, "_sample_xai_once", return_value=FakeResponse()):
            response, attempts = module._run_x_search(
                None,
                prompt="test",
                from_date="2026-08-22",
                to_date="2026-08-25",
            )
        self.assertEqual(attempts, 1)
        self.assertEqual(response.citations, FakeResponse.citations)
        self.assertEqual(response.output_text, FakeResponse.content)

    def test_nonretryable_error_fails_without_hidden_retry(self):
        module = SimpleNamespace(
            _xai_official_sdk_adapter_installed=False,
            MAX_X_SEARCH_ATTEMPTS=2,
        )
        adapter.install_xai_sdk_x_search(module)
        with patch.object(adapter, "_sample_xai_once", side_effect=ValueError("bad request")) as sample:
            with self.assertRaises(ValueError):
                module._run_x_search(
                    None,
                    prompt="test",
                    from_date="2026-08-22",
                    to_date="2026-08-25",
                )
        self.assertEqual(sample.call_count, 1)


if __name__ == "__main__":
    unittest.main()
