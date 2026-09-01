from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("publish_remote_telemetry.py")
SPEC = importlib.util.spec_from_file_location("publish_remote_telemetry", MODULE_PATH)
assert SPEC and SPEC.loader
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


class FakeResponse:
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def read(self, size: int) -> bytes:
        return json.dumps({"accepted": True}).encode()


class PublishRemoteTelemetryTests(unittest.TestCase):
    def _publish_headers(self, bypass_secret: str = "") -> dict[str, str]:
        captured: dict[str, str] = {}

        def capture_request(request: object, timeout: int) -> FakeResponse:
            assert hasattr(request, "header_items")
            captured.update(dict(request.header_items()))
            return FakeResponse()

        with patch.object(publisher.urllib.request, "urlopen", capture_request):
            publisher._publish(
                "https://preview.example/telemetry/ingest",
                "test-ingest-token",
                b"{}",
                bypass_secret,
            )
        return {key.lower(): value for key, value in captured.items()}

    def test_publish_keeps_telemetry_token_without_bypass(self) -> None:
        headers = self._publish_headers()

        self.assertEqual(headers["x-iios-telemetry-token"], "Bearer test-ingest-token")
        self.assertNotIn("x-vercel-protection-bypass", headers)

    def test_publish_sends_optional_vercel_bypass_header(self) -> None:
        headers = self._publish_headers("test-bypass-secret")

        self.assertEqual(headers["x-iios-telemetry-token"], "Bearer test-ingest-token")
        self.assertEqual(headers["x-vercel-protection-bypass"], "test-bypass-secret")


if __name__ == "__main__":
    unittest.main()