import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from intelligence.models import EvidenceItem, EvidencePacket


SEC_CURRENT_FILINGS_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
IPO_FORMS = ("S-1", "S-1/A", "F-1", "F-1/A", "424B4", "EFFECT")


def _sec_user_agent() -> str | None:
    value = os.getenv("SEC_USER_AGENT", "").strip()
    return value or None


def sec_ipo_status() -> dict:
    user_agent = _sec_user_agent()
    return {
        "provider": "sec_edgar_ipo",
        "configured": bool(user_agent),
        "source": "SEC EDGAR Latest Filings RSS/Atom",
        "forms": list(IPO_FORMS),
        "requires": "SEC_USER_AGENT",
        "paper_mode": True,
    }


def _feed_url(form_type: str, count: int) -> str:
    query = urlencode(
        {
            "action": "getcurrent",
            "type": form_type,
            "owner": "include",
            "count": max(1, min(count, 100)),
            "output": "atom",
        }
    )
    return f"{SEC_CURRENT_FILINGS_URL}?{query}"


def _text(node: ET.Element | None) -> str:
    return "" if node is None or node.text is None else node.text.strip()


async def fetch_recent_ipo_filings(count_per_form: int = 25) -> EvidencePacket:
    user_agent = _sec_user_agent()
    if not user_agent:
        raise RuntimeError(
            "SEC_USER_AGENT is required for compliant SEC EDGAR access, "
            "for example 'IIOS research contact@example.com'."
        )

    headers = {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Host": "www.sec.gov",
    }
    items: list[EvidenceItem] = []
    observed_at = datetime.now(timezone.utc)

    async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
        for form_type in IPO_FORMS:
            response = await client.get(_feed_url(form_type, count_per_form))
            response.raise_for_status()
            root = ET.fromstring(response.text)

            namespace = {"a": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("a:entry", namespace):
                title = _text(entry.find("a:title", namespace))
                summary = _text(entry.find("a:summary", namespace))
                updated = _text(entry.find("a:updated", namespace))
                link_node = entry.find("a:link", namespace)
                url = link_node.attrib.get("href") if link_node is not None else None

                published_at = None
                if updated:
                    try:
                        published_at = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    except ValueError:
                        published_at = None

                items.append(
                    EvidenceItem(
                        source_name="SEC EDGAR",
                        source_kind="company",
                        title=title or f"{form_type} filing",
                        url=url,
                        published_at=published_at,
                        observed_at=observed_at,
                        summary=(
                            f"IPO-related SEC filing ({form_type}). {summary}".strip()
                        ),
                        freshness="fresh",
                        confidence=0.99,
                    )
                )

    seen: set[str] = set()
    unique: list[EvidenceItem] = []
    for item in sorted(items, key=lambda value: value.published_at or observed_at, reverse=True):
        key = item.url or item.title
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return EvidencePacket(
        topic="Recent U.S. IPO registration, effectiveness, and final prospectus filings",
        items=unique,
    )
