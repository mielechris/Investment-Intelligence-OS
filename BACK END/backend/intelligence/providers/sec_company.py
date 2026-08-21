import asyncio
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from intelligence.models import EvidenceItem, EvidencePacket


SEC_CURRENT_FILINGS_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
COMPANY_FORMS = ("8-K", "10-Q", "10-K", "4")
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _user_agent() -> str | None:
    value = os.getenv("SEC_USER_AGENT", "").strip()
    return value or None


def _url(form_type: str, count: int) -> str:
    return f"{SEC_CURRENT_FILINGS_URL}?{urlencode({'action':'getcurrent','type':form_type,'owner':'include','count':max(1,min(count,100)),'output':'atom'})}"


async def _get_with_backoff(client: httpx.AsyncClient, url: str, attempts: int = 4) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = await client.get(url)
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response
            last_error = RuntimeError(f"SEC returned HTTP {response.status_code}")
            retry_after = response.headers.get("Retry-After", "")
            delay = min(float(retry_after), 15.0) if retry_after.isdigit() else min(2 ** attempt, 8)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            last_error = exc
            delay = min(2 ** attempt, 8)
        if attempt < attempts - 1:
            await asyncio.sleep(delay)
    raise RuntimeError(str(last_error) or repr(last_error) or "SEC request failed after retries")


async def fetch_recent_company_filings(count_per_form: int = 40) -> EvidencePacket:
    user_agent = _user_agent()
    if not user_agent:
        raise RuntimeError("SEC_USER_AGENT is required for compliant SEC EDGAR access")

    items: list[EvidenceItem] = []
    now = datetime.now(timezone.utc)
    headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
    namespace = {"a": "http://www.w3.org/2005/Atom"}
    successful_forms = 0
    failures: list[str] = []

    async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
        for form_type in COMPANY_FORMS:
            try:
                response = await _get_with_backoff(client, _url(form_type, count_per_form))
                successful_forms += 1
            except Exception as exc:
                failures.append(f"{form_type}: {str(exc) or repr(exc)}")
                continue

            root = ET.fromstring(response.text)
            for entry in root.findall("a:entry", namespace):
                title_node = entry.find("a:title", namespace)
                summary_node = entry.find("a:summary", namespace)
                updated_node = entry.find("a:updated", namespace)
                link_node = entry.find("a:link", namespace)
                title = (title_node.text or "").strip() if title_node is not None else ""
                summary = (summary_node.text or "").strip() if summary_node is not None else ""
                updated = (updated_node.text or "").strip() if updated_node is not None else ""
                published_at = None
                if updated:
                    try:
                        published_at = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    except ValueError:
                        pass
                items.append(EvidenceItem(
                    source_name="SEC EDGAR",
                    source_kind="company",
                    title=title or f"{form_type} filing",
                    url=link_node.attrib.get("href") if link_node is not None else None,
                    published_at=published_at,
                    observed_at=now,
                    summary=f"Company filing ({form_type}). {summary}".strip(),
                    freshness="fresh",
                    confidence=0.99,
                ))

    if successful_forms == 0 and failures:
        raise RuntimeError("All SEC company form requests failed after retries: " + " | ".join(failures))

    return EvidencePacket(topic="Recent U.S. public-company filings and insider activity", items=items)
