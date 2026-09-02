from __future__ import annotations

from typing import Any


COMPAT_VERSION = "xai-untyped-parse-citations-v3"


class _ResponseWithRawCitations:
    """Delegate parsed SDK response behavior while preserving raw xAI source metadata."""

    def __init__(self, parsed: Any, raw_payload: dict[str, Any]):
        self._parsed = parsed
        self.citations = raw_payload.get("citations") if isinstance(raw_payload, dict) else None
        self.sources = raw_payload.get("sources") if isinstance(raw_payload, dict) else None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._parsed, name)

    def model_dump(self, *args, **kwargs):
        if hasattr(self._parsed, "model_dump"):
            return self._parsed.model_dump(*args, **kwargs)
        return {}


def _direct_urls(response: Any, module) -> set[str]:
    """Read xAI citation/source attributes without trusting model-authored prose URLs."""
    found: set[str] = set()
    for name in ("citations", "sources"):
        value = getattr(response, name, None)
        if value is None and isinstance(response, dict):
            value = response.get(name)
        found.update(module._urls_from_value(value))

    extra = getattr(response, "__pydantic_extra__", None)
    if isinstance(extra, dict):
        for name in ("citations", "sources"):
            found.update(module._urls_from_value(extra.get(name)))

    output: set[str] = set()
    for value in found:
        normalized = module._normalize_url(value)
        if normalized and module._is_x_url(normalized):
            output.add(normalized)
    return output


def _install_raw_x_search(module) -> None:
    """Do not replace the governed request boundary with a raw SDK transport."""
    module._xai_raw_x_search_installed = False
    module._xai_raw_x_search_skipped_for_cost_governor = True


def install_grok_citation_compat(module) -> None:
    """Capture raw xAI citations and extend extraction without trusting model prose."""
    if getattr(module, "_xai_citation_compat_installed", False):
        return
    module._xai_citation_compat_installed = True

    original = module._extract_citation_urls

    def compatible_extract(response: Any) -> set[str]:
        return set(original(response)) | _direct_urls(response, module)

    module._extract_citation_urls = compatible_extract
    _install_raw_x_search(module)
