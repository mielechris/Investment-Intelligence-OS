from __future__ import annotations

from typing import Any


COMPAT_VERSION = "xai-top-level-citations-v1"


def _direct_urls(response: Any, module) -> set[str]:
    """Read xAI citation/source attributes directly from the response object.

    xAI documents `response.citations` as the complete source list for agent-tool
    requests. Some OpenAI SDK serialization paths do not include that extra field in
    `model_dump()`, so the main parser can otherwise miss valid X citations.
    """
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


def install_grok_citation_compat(module) -> None:
    """Extend citation extraction without trusting model-authored prose URLs."""
    if getattr(module, "_xai_citation_compat_installed", False):
        return
    module._xai_citation_compat_installed = True

    original = module._extract_citation_urls

    def compatible_extract(response: Any) -> set[str]:
        return set(original(response)) | _direct_urls(response, module)

    module._extract_citation_urls = compatible_extract
