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

    def test_installer_never_replaces_the_governed_x_search_transport(self):
        original = object()
        module = SimpleNamespace(
            _xai_official_sdk_adapter_installed=False,
            MAX_X_SEARCH_ATTEMPTS=2,
            _run_x_search=original,
        )
        adapter.install_xai_sdk_x_search(module)
        self.assertFalse(module._xai_official_sdk_adapter_installed)
        self.assertTrue(module._xai_official_sdk_adapter_skipped_for_cost_governor)
        self.assertIs(module._run_x_search, original)

    def test_nonbinding_plan_cannot_enable_ungoverned_sdk_transport(self):
        original = object()
        module = SimpleNamespace(
            _xai_official_sdk_adapter_installed=False,
            _run_x_search=original,
            grok_plan=lambda: {"cost_governor_binding": False},
        )
        adapter.install_xai_sdk_x_search(module)
        self.assertFalse(module._xai_official_sdk_adapter_installed)
        self.assertIs(module._run_x_search, original)

    def test_installer_skips_sdk_transport_when_governed_boundary_is_binding(self):
        original_run_x_search = object()
        module = SimpleNamespace(
            _xai_official_sdk_adapter_installed=False,
            _run_x_search=original_run_x_search,
            grok_plan=lambda: {"cost_governor_binding": True},
        )

        adapter.install_xai_sdk_x_search(module)

        self.assertFalse(module._xai_official_sdk_adapter_installed)
        self.assertTrue(module._xai_official_sdk_adapter_skipped_for_cost_governor)
        self.assertIs(module._run_x_search, original_run_x_search)


if __name__ == "__main__":
    unittest.main()
