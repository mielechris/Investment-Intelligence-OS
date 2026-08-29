from __future__ import annotations

import unittest

import iios_historical_market_intelligence_runtime as runtime


class Batch10HSystemTrustRuntimeTest(unittest.TestCase):
    def test_yahoo_history_conversion_preserves_real_rows(self) -> None:
        payload = {
            "chart": {
                "result": [{
                    "timestamp": [1609459200 + 86400 * i for i in range(120)],
                    "indicators": {"quote": [{
                        "open": [100.0 + i for i in range(120)],
                        "high": [101.0 + i for i in range(120)],
                        "low": [99.0 + i for i in range(120)],
                        "close": [100.5 + i for i in range(120)],
                        "volume": [1_000_000 + i for i in range(120)],
                    }]},
                }]
            }
        }
        text = runtime._yahoo_json_to_csv(payload)
        self.assertIn("Date,Open,High,Low,Close,Volume", text)
        self.assertGreaterEqual(len(text.strip().splitlines()) - 1, 100)

    def test_system_curl_command_never_disables_tls(self) -> None:
        source = runtime._curl_text.__code__.co_consts
        flattened = " ".join(str(value) for value in source)
        self.assertNotIn("--insecure", flattened)
        self.assertNotIn(" -k ", f" {flattened} ")


if __name__ == "__main__":
    unittest.main()
