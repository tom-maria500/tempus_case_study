"""Pre-call intel digest via web search + LLM synthesis."""

from __future__ import annotations

import base64
import re
import time
import urllib.request
from urllib.parse import parse_qs, unquote, urlparse

from datetime import date, timedelta

from models import IntelItem, IntelRequest, IntelResponse

from rag import (
    _call_llm_for_brief,
    _find_physician_row,
    _load_market_dataframe,
    _retrieve_crm_for_physician,
    _init_vector_index,
)


def _get_physician_with_context(physician_id: str) -> dict | None:
    """Load physician profile + CRM objections."""
    df = _load_market_dataframe()
    row = _find_physician_row(df, None, physician_id)
    if row is None:
        return None

    last_contact = row.get("last_contact_date")
    last_str = ""
    if last_contact is not None and str(last_contact).strip():
        last_str = str(last_contact).split()[0]

    objections = ""
    try:
        index, _ = _init_vector_index()
        crm_nodes = _retrieve_crm_for_physician(
            index, str(row["name"]), str(row["physician_id"])
        )
        for node in crm_nodes:
            obj = node.node.metadata.get("objections")
            if obj:
                objections += str(obj) + " "
    except Exception:
        pass

    return {
        "physician_id": str(row["physician_id"]),
        "name": str(row["name"]),
        "specialty": str(row["specialty"]),
        "institution": str(row["institution"]),
        "primary_cancer_focus": str(row.get("primary_cancer_focus", "")),
        "last_contact_date": last_str,
        "objections_from_crm": objections.strip() or "Unknown",
    }


def _unwrap_redirect_url(url: str) -> str:
    """Extract actual destination from search-engine redirect URLs."""
    if not url or not url.strip():
        return url
    url = url.strip()
    # Normalize relative DDG links
    if url.startswith("/") and "uddg=" in url:
        url = "https://duckduckgo.com" + url
    try:
        parsed = urlparse(url)
        # DuckDuckGo: .../l?... or .../l/?uddg=...
        if "/l" in parsed.path:
            qs = parse_qs(parsed.query)
            uddg = qs.get("uddg")
            if uddg and isinstance(uddg, list) and uddg[0]:
                return unquote(uddg[0])
        # Bing: bing.com/ck/a?u=base64...
        if "bing.com" in parsed.netloc and "/ck/a" in parsed.path:
            qs = parse_qs(parsed.query)
            u = qs.get("u", [""])[0]
            if u and len(u) > 2:
                try:
                    decoded = base64.urlsafe_b64decode(u[2:] + "=" * ((-len(u) + 2) % 4)).decode()
                    return decoded
                except Exception:
                    pass
    except Exception:
        pass
    return url


def _resolve_final_url(url: str, timeout: float = 3.0) -> str:
    """Follow redirects and return the final URL; return original on any failure."""
    if not url or not url.startswith(("http://", "https://")):
        return url or ""
    ua = "Mozilla/5.0 (compatible; TempusCopilot/1.0)"
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.geturl() or url
    except Exception:
        try:
            req = urllib.request.Request(url, method="GET", headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.geturl() or url
        except Exception:
            return url


def _run_web_search(query: str, max_results: int = 5) -> list[dict]:
    """Run web search and return snippets + URLs."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [
            {"title": r.get("title", ""), "body": r.get("body", ""), "href": r.get("href", "")}
            for r in results
        ]
    except Exception:
        return []


def fetch_intel(request: IntelRequest) -> IntelResponse:
    """Build pre-call intel digest via web search + LLM synthesis."""
    physician = _get_physician_with_context(request.physician_id)
    if physician is None:
        raise ValueError(f"Physician {request.physician_id} not found")

    days = request.days_lookback
    last = physician.get("last_contact_date", "")
    if last:
        try:
            base = date.fromisoformat(str(last).split()[0])
        except (ValueError, TypeError):
            base = date.today()
    else:
        base = date.today()

    days_since = (date.today() - base).days
    lookback_date = (date.today() - timedelta(days=days)).isoformat()

    # Run parallel searches (simplified: sequential for demo)
    cancer = physician["primary_cancer_focus"] or "oncology"
    name = physician["name"]
    search_queries = [
        f"FDA approval {cancer} oncology {lookback_date}",
        f"{name} publication oncology journal",
        "Tempus AI TIME Trial xF xT NSCLC data 2025",
        f"Foundation Medicine Guardant {cancer} 2025",
    ]

    search_results: list[dict] = []
    for q in search_queries:
        hits = _run_web_search(q, max_results=3)
        search_results.extend([{"query": q, "results": hits}])

    # Build flat list of (title, body, url); unwrap redirects, then resolve to final URL
    all_hits: list[dict] = []
    for s in search_results:
        for r in s["results"]:
            href = (r.get("href") or "").strip()
            if href and not href.startswith(("http://", "https://")):
                href = "https://duckduckgo.com" + (href if href.startswith("/") else "/" + href)
            url = _unwrap_redirect_url(href) if href else ""
            if not url:
                url = href
            # If still a redirect-style URL, resolve to final destination
            if url and ("duckduckgo.com/l" in url or "bing.com/ck/a" in url):
                resolved = _resolve_final_url(url)
                url = resolved if resolved else url
            all_hits.append({
                "title": r.get("title", ""),
                "body": (r.get("body") or "")[:300],
                "url": url or "",
            })
    raw_text = "\n".join(
        f"[{i}] {h['title']}: {h['body']}..."
        for i, h in enumerate(all_hits, start=1)
    )

    prompt = f"""You are preparing a pre-call intel digest for a Tempus sales rep meeting with {physician['name']}, a {physician['specialty']} at {physician['institution']}.

Their primary cancer focus: {physician['primary_cancer_focus']}
Last contact: {physician['last_contact_date'] or 'Unknown'}
Known objections: {physician['objections_from_crm']}

Search results (use source_index to cite which result [1]-[N] each item comes from):
{raw_text[:12000]}

Return JSON only:
{{
  "drug_updates": [{{"headline": "...", "detail": "...", "relevance": "...", "source_index": 1, "date": "YYYY-MM-DD"}}],
  "publications": [{{"headline": "...", "detail": "...", "relevance": "...", "source_index": 2, "date": "..."}}],
  "tempus_updates": [{{"headline": "...", "detail": "...", "relevance": "...", "source_index": 3, "date": "..."}}],
  "competitive_intel": [{{"headline": "...", "detail": "...", "relevance": "...", "source_index": 4, "date": "..."}}]
}}

Each item: headline, detail (2-3 sentences), relevance (why this matters for THIS physician), source_index (the [N] from the search results, 1-based), date.
Only use source_index values that exist in the results above. If no good match, omit source_index or use null.
"""

    try:
        raw = _call_llm_for_brief(prompt)
    except Exception:
        raw = {
            "drug_updates": [],
            "publications": [],
            "tempus_updates": [],
            "competitive_intel": [],
        }

    def to_items(lst: list, url_by_index: dict[int, str]) -> list[IntelItem]:
        out = []
        for x in lst if isinstance(lst, list) else []:
            if isinstance(x, dict):
                idx = x.get("source_index")
                try:
                    idx_int = int(idx) if idx is not None else None
                except (TypeError, ValueError):
                    idx_int = None
                if idx_int is not None and idx_int in url_by_index:
                    raw_url = url_by_index[idx_int]
                else:
                    raw_url = str(x.get("source_url", "")).strip()
                    if raw_url:
                        raw_url = re.sub(r"^url:\s*", "", raw_url, flags=re.IGNORECASE)
                        if not raw_url.startswith(("http://", "https://")) and "http" in raw_url:
                            match = re.search(r"https?://\S+", raw_url)
                            if match:
                                raw_url = match.group(0)
                        raw_url = _unwrap_redirect_url(raw_url)
                    else:
                        raw_url = ""
                out.append(
                    IntelItem(
                        headline=str(x.get("headline", ""))[:200],
                        detail=str(x.get("detail", ""))[:800],
                        relevance=str(x.get("relevance", ""))[:400],
                        source_url=(raw_url or "")[:500],
                        date=str(x.get("date", "")),
                    )
                )
        return out

    url_by_index = {
        i: (h.get("url") or "").strip()
        for i, h in enumerate(all_hits, start=1)
        if (h.get("url") or "").strip().startswith(("http://", "https://"))
    }
    return IntelResponse(
        physician_name=physician["name"],
        last_contact_date=physician.get("last_contact_date") or "Unknown",
        days_since_contact=days_since,
        drug_updates=to_items(raw.get("drug_updates", []), url_by_index),
        publications=to_items(raw.get("publications", []), url_by_index),
        tempus_updates=to_items(raw.get("tempus_updates", []), url_by_index),
        competitive_intel=to_items(raw.get("competitive_intel", []), url_by_index),
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
