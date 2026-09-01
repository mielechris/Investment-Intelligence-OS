from __future__ import annotations

import os
from datetime import datetime
from typing import Any


ADAPTER_VERSION = "xai-official-sdk-citations-v5-cost-governor-aware"


class _XaiSdkResponseAdapter:
    """Expose the small Responses-like surface IIOS already consumes."""

    def __init__(self, response: Any):
        self._response = response
        self.output_text = str(getattr(response, "content", "") or "")
        self.citations = list(getattr(response, "citations", None) or [])
        self.sources = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._response, name)

    def model_dump(self, *args, **kwargs) -> dict[str, Any]:
        usage = getattr(self._response, "usage", None)
        try:
            cost_ticks = int(getattr(usage, "cost_in_usd_ticks", 0) or 0)
        except (TypeError, ValueError):
            cost_ticks = 0

        def usage_int(primary: str, fallback: str | None = None) -> int:
            value = getattr(usage, primary, None)
            if value is None and fallback:
                value = getattr(usage, fallback, 0)
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        input_tokens = usage_int("input_tokens", "prompt_tokens")
        output_tokens = usage_int("output_tokens", "completion_tokens")
        cached_tokens = 0
        details = getattr(usage, "input_tokens_details", None) or getattr(usage, "prompt_tokens_details", None)
        try:
            cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)
        except (TypeError, ValueError):
            cached_tokens = 0

        server_usage = getattr(self._response, "server_side_tool_usage", None)
        tool_count = 0
        if isinstance(server_usage, dict):
            for value in server_usage.values():
                try:
                    tool_count += int(value or 0)
                except (TypeError, ValueError):
                    pass
        else:
            try:
                tool_count = int(getattr(usage, "num_server_side_tools_used", 0) or 0)
            except (TypeError, ValueError):
                tool_count = 0

        return {
            "citations": list(self.citations),
            "usage": {
                "input_tokens": input_tokens,
                "input_tokens_details": {"cached_tokens": cached_tokens},
                "output_tokens": output_tokens,
                "cost_in_usd_ticks": cost_ticks,
                "num_server_side_tools_used": tool_count,
            },
        }


def _parse_date(value: str) -> datetime:
    return datetime.fromisoformat(str(value))


def _sample_xai_once(module, *, prompt: str, from_date: str, to_date: str):
    """Call xAI through its official SDK, which exposes response.citations directly."""
    from xai_sdk import Client
    from xai_sdk.chat import user
    from xai_sdk.tools import x_search

    client = Client(
        api_key=os.getenv("XAI_API_KEY"),
        timeout=module.grok_timeout_seconds(),
        channel_options=[("grpc.enable_retries", 0)],
    )
    chat = client.chat.create(
        model=module.grok_model(),
        tools=[
            x_search(
                from_date=_parse_date(from_date),
                to_date=_parse_date(to_date),
            )
        ],
    )
    chat.append(user(prompt))
    return chat.sample()


def _retryable_xai_error(exc: Exception) -> bool:
    try:
        import grpc

        if isinstance(exc, grpc.RpcError):
            code = exc.code()
            return code in {grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.UNAVAILABLE}
    except Exception:
        pass
    return False


def install_xai_sdk_x_search(module) -> None:
    """Install the official xAI SDK transport only when no binding cost gate owns the boundary.

    Once Batch 10M cost enforcement is active, the governed OpenAI-compatible
    Responses boundary remains authoritative because it carries pre-call admission,
    prompt caching, tool-call caps, output caps, and exact post-call accounting.
    This prevents a later SDK adapter install from silently bypassing the governor.
    """
    try:
        plan = module.grok_plan()
    except Exception:
        plan = {}
    if isinstance(plan, dict) and plan.get("cost_governor_binding") is True:
        module._xai_official_sdk_adapter_installed = False
        module._xai_official_sdk_adapter_skipped_for_cost_governor = True
        return

    if getattr(module, "_xai_official_sdk_adapter_installed", False):
        return
    module._xai_official_sdk_adapter_installed = True

    def official_x_search(
        _openai_client,
        *,
        prompt: str,
        from_date: str,
        to_date: str,
        case_id: str | None = None,
        query_label: str | None = None,
    ):
        del case_id, query_label
        last_error: Exception | None = None
        for attempt in range(1, module.MAX_X_SEARCH_ATTEMPTS + 1):
            try:
                response = _sample_xai_once(
                    module,
                    prompt=prompt,
                    from_date=from_date,
                    to_date=to_date,
                )
                return _XaiSdkResponseAdapter(response), attempt
            except Exception as exc:
                last_error = exc
                if attempt >= module.MAX_X_SEARCH_ATTEMPTS or not _retryable_xai_error(exc):
                    raise
        raise last_error or RuntimeError("Grok X Search failed")

    module._run_x_search = official_x_search
