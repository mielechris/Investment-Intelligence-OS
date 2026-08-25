from __future__ import annotations

from typing import Any


COMPAT_VERSION = "xai-raw-response-citations-v2"


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
    """Capture raw xAI JSON before OpenAI SDK model parsing can drop extension fields."""
    if getattr(module, "_xai_raw_x_search_installed", False):
        return
    module._xai_raw_x_search_installed = True

    def raw_x_search(client, *, prompt: str, from_date: str, to_date: str):
        last_error: Exception | None = None
        for attempt in range(1, module.MAX_X_SEARCH_ATTEMPTS + 1):
            try:
                raw = client.responses.with_raw_response.create(
                    model=module.grok_model(),
                    input=prompt,
                    tools=[{"type": "x_search", "from_date": from_date, "to_date": to_date}],
                )
                try:
                    raw_payload = raw.http_response.json()
                except Exception:
                    raw_payload = {}
                parsed = raw.parse()
                return _ResponseWithRawCitations(parsed, raw_payload), attempt
            except module.APITimeoutError as exc:
                last_error = exc
                if attempt >= module.MAX_X_SEARCH_ATTEMPTS:
                    raise
        raise last_error or RuntimeError("Grok X Search failed")

    module._run_x_search = raw_x_search


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
