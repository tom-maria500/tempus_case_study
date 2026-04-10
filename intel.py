"""Pre-call intel digest via web search + LLM synthesis."""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.request
from urllib.parse import parse_qs, unquote, urlencode, urlparse

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
    """Load physician profile + CRM objections, tags, and interests for relevance."""
    df = _load_market_dataframe()
    row = _find_physician_row(df, None, physician_id)
    if row is None:
        return None

    last_contact = row.get("last_contact_date")
    last_str = ""
    if last_contact is not None and str(last_contact).strip():
        last_str = str(last_contact).split()[0]

    objections = ""
    objection_tags = ""
    interests = ""
    try:
        index, _ = _init_vector_index()
        crm_nodes = _retrieve_crm_for_physician(
            index, str(row["name"]), str(row["physician_id"])
        )
        summary_nodes: list = []
        for n in crm_nodes:
            try:
                dt = str(n.node.metadata.get("doc_type") or "")  # type: ignore[attr-defined]
            except Exception:
                dt = ""
            if dt == "crm_summary":
                summary_nodes.append(n)
        use_nodes = summary_nodes if summary_nodes else crm_nodes[:1]
        for node in use_nodes:
            try:
                meta = node.node.metadata  # type: ignore[attr-defined]
            except Exception:
                meta = {}
            if not objection_tags:
                objection_tags = str(meta.get("objection_tags") or "").strip()
            obj = meta.get("objections")
            if obj:
                objections = str(obj).strip()
            intr = meta.get("interests")
            if intr:
                interests = str(intr).strip()
            break
    except Exception:
        pass

    return {
        "physician_id": str(row["physician_id"]),
        "name": str(row["name"]),
        "specialty": str(row["specialty"]),
        "institution": str(row["institution"]),
        "city": str(row.get("city", "")),
        "state": str(row.get("state", "")),
        "primary_cancer_focus": str(row.get("primary_cancer_focus", "")),
        "last_contact_date": last_str,
        "objections_from_crm": objections.strip() or "Unknown",
        "objection_tags": objection_tags,
        "interests_from_crm": interests.strip() or "",
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


def _run_web_search(
    query: str, max_results: int = 5, timelimit: str | None = None
) -> list[dict]:
    """Run web search and return snippets + URLs.

    timelimit: DDGS coarse bucket d|w|m|y when supported; not an exact calendar range.
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            if timelimit is not None:
                try:
                    results = list(
                        ddgs.text(query, max_results=max_results, timelimit=timelimit)
                    )
                except TypeError:
                    results = list(ddgs.text(query, max_results=max_results))
            else:
                results = list(ddgs.text(query, max_results=max_results))
        return [
            {
                "title": r.get("title", ""),
                "body": r.get("body", ""),
                "href": r.get("href", ""),
                "date": str(r.get("date", "")).strip(),
            }
            for r in results
        ]
    except Exception:
        return []


def _run_ddgs_news(
    query: str, max_results: int = 5, timelimit: str | None = None
) -> list[dict]:
    """News metasearch (DDGS): better-dated headlines than generic web text search."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            tl = timelimit
            if tl == "y":
                tl = "m"
            kwargs: dict = {"max_results": max_results}
            if tl is not None:
                kwargs["timelimit"] = tl
            try:
                results = list(ddgs.news(query, **kwargs))
            except TypeError:
                results = list(ddgs.news(query, max_results=max_results))
        out: list[dict] = []
        for r in results:
            url = str(r.get("url") or r.get("href") or "").strip()
            out.append(
                {
                    "title": r.get("title", ""),
                    "body": r.get("body", ""),
                    "href": url,
                    "date": str(r.get("date", "")).strip(),
                }
            )
        return out
    except Exception:
        return []


def _run_newsapi_everything(
    api_key: str,
    query: str,
    start_dt: date,
    end_dt: date,
    page_size: int = 10,
) -> list[dict]:
    """NewsAPI.org /v2/everything — optional; requires NEWS_API_KEY and (on free tier) dev rules."""
    if not api_key.strip():
        return []
    try:
        params = {
            "q": query,
            "from": start_dt.isoformat(),
            "to": end_dt.isoformat(),
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": min(max(page_size, 1), 100),
            "apiKey": api_key.strip(),
        }
        url = f"https://newsapi.org/v2/everything?{urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "TempusCopilot/1.0"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") != "ok":
            return []
        out: list[dict] = []
        for art in data.get("articles") or []:
            title = str(art.get("title") or "")
            desc = str(art.get("description") or "") or str(art.get("content") or "")
            url_a = str(art.get("url") or "")
            pub = str(art.get("publishedAt") or "")
            date_str = pub[:10] if len(pub) >= 10 else ""
            out.append(
                {
                    "title": title,
                    "body": desc[:400],
                    "href": url_a,
                    "date": date_str,
                }
            )
        return out
    except Exception:
        return []


def _ddg_news_timelimit(ddg_text_tl: str | None) -> str | None:
    """DDGS news() supports d, w, m only (not y)."""
    if ddg_text_tl is None:
        return None
    if ddg_text_tl == "y":
        return "m"
    return ddg_text_tl


def _hit_from_search_row(r: dict, origin: str) -> dict | None:
    """Normalize a search/news row to a unified hit with http(s) URL."""
    href = (r.get("href") or r.get("url") or "").strip()
    if not href:
        return None
    if not href.startswith(("http://", "https://")):
        href = "https://duckduckgo.com" + (href if href.startswith("/") else "/" + href)
    url = _unwrap_redirect_url(href) if href else ""
    if not url:
        url = href
    if url and ("duckduckgo.com/l" in url or "bing.com/ck/a" in url):
        resolved = _resolve_final_url(url)
        url = resolved if resolved else url
    if not url.startswith(("http://", "https://")):
        return None
    return {
        "title": str(r.get("title", "")),
        "body": (str(r.get("body") or ""))[:400],
        "url": url,
        "date": str(r.get("date", "")).strip(),
        "_origin": origin,
    }


def _parse_month_day_year(text: str) -> date | None:
    """Parse 'Jan 15, 2024' / 'January 15, 2024' style dates in snippets."""
    m = re.search(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2}),?\s+(\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    abbr = m.group(1).lower()[:3]
    month_map = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    mo = month_map.get(abbr)
    if not mo:
        return None
    try:
        return date(int(m.group(3)), mo, int(m.group(2)))
    except Exception:
        return None


def _parse_result_date(value: str) -> date | None:
    """Best-effort date parsing from search result metadata/snippets."""
    if not value:
        return None
    text = value.strip()
    # ISO date or datetime (e.g. 2024-07-03T16:25:22+00:00)
    if len(text) >= 10:
        try:
            return date.fromisoformat(text[:10])
        except Exception:
            pass
    # YYYY/MM/DD and YYYY.MM.DD
    m = re.search(r"\b(\d{4})[\/\.-](\d{2})[\/\.-](\d{2})\b", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            return None
    return _parse_month_day_year(text)


def _ddg_timelimit_for_window(start_dt: date, end_dt: date) -> str | None:
    """Best-effort DDGS text() timelimit: d/w/m/y. Only when window ends near today.

    Arbitrary historical ranges (e.g. all of 2024) cannot be expressed; returns None.
    """
    today = date.today()
    effective_end = min(end_dt, today)
    if effective_end < today - timedelta(days=14):
        return None
    span_days = max(1, (effective_end - start_dt).days + 1)
    if span_days <= 2 and effective_end >= today - timedelta(days=2):
        return "d"
    if span_days <= 14:
        return "w"
    if span_days <= 45:
        return "m"
    return "y"


def _intel_item_resolved_date(x: dict, hits_by_index: dict[int, dict] | None) -> date | None:
    """Date used for window filtering: search hit (by source_index) first, then LLM."""
    idx = x.get("source_index")
    try:
        idx_int = int(idx) if idx is not None else None
    except (TypeError, ValueError):
        idx_int = None
    if hits_by_index and idx_int is not None:
        hit = hits_by_index.get(idx_int)
        if hit:
            p = _parse_result_date(str(hit.get("date", "") or ""))
            if p:
                return p
            p = _parse_result_date(f"{hit.get('title', '')} {hit.get('body', '')}")
            if p:
                return p
    return _parse_result_date(str(x.get("date", "")).strip())


def _last_name_from_display_name(name: str) -> str:
    cleaned = re.sub(r"^Dr\.?\s*", "", (name or "").strip(), flags=re.IGNORECASE)
    parts = cleaned.split()
    return parts[-1] if parts else ""


def _boost_terms_from_physician(physician: dict) -> list[str]:
    """Terms that should increase hit scores when present in search snippets."""
    terms: list[str] = []
    for part in re.split(r"[,;/\s]+", physician.get("primary_cancer_focus") or ""):
        p = part.strip().lower()
        if len(p) >= 3:
            terms.append(p)
    spec = (physician.get("specialty") or "").lower()
    for w in ("nsclc", "lung", "breast", "colorectal", "gi", "thoracic", "melanoma", "lymphoma"):
        if w in spec:
            terms.append(w)
    tags = (physician.get("objection_tags") or "").lower()
    tag_map = {
        "turnaround_time": ["turnaround", "tat", "timeline"],
        "cost_reimbursement": ["reimbursement", "coverage", "medicare", "adlt"],
        "competitor_loyalty": ["foundation", "guardant", "comprehensive genomic"],
        "emr_integration": ["epic", "ehr", "electronic health"],
        "staff_bandwidth": ["prior authorization", "coordinator", "workflow"],
        "ai_skepticism": ["validation", "fda", "evidence", "clinical"],
    }
    for tag, words in tag_map.items():
        if tag in tags:
            terms.extend(words)
    return list(dict.fromkeys(terms))[:25]


def _build_news_queries(physician: dict) -> list[str]:
    """Shorter queries for news indexes (FDA, Tempus, comps, reimbursement)."""
    cancer = physician.get("primary_cancer_focus") or "oncology"
    spec = physician.get("specialty") or "oncology"
    institution = physician.get("institution") or ""
    last = _last_name_from_display_name(physician.get("name", ""))
    tags = (physician.get("objection_tags") or "").lower()
    queries = [
        f"FDA approval {cancer} oncology",
        f"Tempus {cancer} genomic",
        f"Medicare genomic profiling reimbursement {cancer}",
        f"Foundation Medicine Guardant {cancer} liquid biopsy",
    ]
    if last and institution:
        queries.append(f'"{last}" {spec} {institution}')
    if "turnaround_time" in tags or "tat" in (physician.get("objections_from_crm") or "").lower():
        queries.append(f"oncology lab test turnaround {cancer}")
    return queries[:6]


def _score_hit_relevance(hit: dict, physician: dict, boost_terms: list[str]) -> float:
    """Lightweight lexical score so we rank sources before LLM synthesis."""
    text = f"{hit.get('title', '')} {hit.get('body', '')}".lower()
    score = 0.0
    if not text.strip():
        return -10.0
    for term in boost_terms:
        if len(term) >= 3 and term in text:
            score += 1.2
    last = _last_name_from_display_name(physician.get("name", "")).lower()
    if last and len(last) >= 3 and last in text:
        score += 2.0
    inst = (physician.get("institution") or "").lower()
    if inst and len(inst) > 5:
        inst_short = inst.split()[0]
        if inst_short in text:
            score += 1.5
    for brand in ("tempus", "foundation medicine", "guardant", "fda", "oncology"):
        if brand in text:
            score += 0.8
    junk = ("recipe", "career", "sports", "stock price", "reddit")
    if any(j in text for j in junk):
        score -= 4.0
    origin = hit.get("_origin")
    if origin in ("ddgs_news", "newsapi"):
        score += 0.6
    if _is_tempus_qualified_hit(hit):
        score += 2.5
    return score


def _dedupe_hits_by_url(hits: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for h in hits:
        u = (h.get("url") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(h)
    return out


def _is_tempus_qualified_hit(hit: dict) -> bool:
    """True if the source is attributable to Tempus (official domain or explicit Tempus mention)."""
    url = (hit.get("url") or "").lower()
    if "tempus.com" in url or "tempus.ai" in url:
        return True
    blob = f"{hit.get('title', '')} {hit.get('body', '')} {url}".lower()
    if re.search(r"\btempus\b", blob, re.IGNORECASE):
        return True
    return False


def _filter_tempus_items_to_qualified_sources(
    items: list,
    hits_by_index: dict[int, dict] | None,
) -> list:
    """Drop tempus_updates rows whose source_index does not cite a Tempus-qualified hit."""
    if not hits_by_index:
        return []
    out: list = []
    for x in items if isinstance(items, list) else []:
        if not isinstance(x, dict):
            continue
        idx = x.get("source_index")
        try:
            idx_int = int(idx) if idx is not None else None
        except (TypeError, ValueError):
            idx_int = None
        if idx_int is None:
            continue
        hit = hits_by_index.get(idx_int)
        if hit and _is_tempus_qualified_hit(hit):
            out.append(x)
    return out


def _build_tempus_source_queries(physician: dict, date_window_text: str) -> list[str]:
    """Queries biased toward tempus.com and explicit Tempus branding."""
    cancer = physician.get("primary_cancer_focus") or "oncology"
    return [
        f"site:tempus.com {cancer}",
        f"site:tempus.com trial OR study OR FDA OR partnership",
        f"Tempus AI xR oncology {date_window_text}",
    ]


def _build_intel_search_queries(physician: dict, date_window_text: str) -> list[str]:
    """Targeted queries: cancer, specialty, reimbursement, Tempus, comps, optional TAT."""
    cancer = physician.get("primary_cancer_focus") or "oncology"
    spec = physician.get("specialty") or "oncology"
    institution = physician.get("institution") or ""
    last = _last_name_from_display_name(physician.get("name", ""))
    tags = (physician.get("objection_tags") or "").lower()
    queries = [
        f"FDA approval {cancer} oncology {date_window_text}",
        f"Tempus TIME trial real-world {cancer} genomic {date_window_text}",
        f"comprehensive genomic profiling Medicare reimbursement {cancer} {date_window_text}",
        f'"{last}" {spec} {institution} publication OR research {date_window_text}',
        f"Foundation Medicine Guardant Health {cancer} liquid biopsy comparison {date_window_text}",
    ]
    if "turnaround_time" in tags or "tat" in (physician.get("objections_from_crm") or "").lower():
        queries.append(
            f"oncology comprehensive panel turnaround time days sample receipt {cancer} {date_window_text}"
        )
    return queries[:8]


def _filter_intel_items_by_date_window(
    items: list,
    start_dt: date,
    end_dt: date,
    hits_by_index: dict[int, dict] | None = None,
) -> list:
    """Keep undated items, but drop dated items outside selected window."""
    out: list = []
    for x in items if isinstance(items, list) else []:
        if not isinstance(x, dict):
            continue
        parsed = _intel_item_resolved_date(x, hits_by_index)
        if parsed is None or (start_dt <= parsed <= end_dt):
            out.append(x)
    return out


def _display_date_for_hit(hit: dict | None, llm_date: str) -> str:
    """Prefer search API date on the hit, then LLM, then parsed snippet date."""
    d = str(llm_date or "").strip()
    if hit:
        h = str(hit.get("date", "") or "").strip()
        if h:
            return h[:120]
    if d:
        return d[:120]
    if hit:
        combined = f"{hit.get('title', '')} {hit.get('body', '')}"
        parsed = _parse_result_date(combined)
        if parsed:
            return parsed.isoformat()
    return ""


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
    if request.start_date and request.end_date:
        start_dt = min(request.start_date, request.end_date)
        end_dt = max(request.start_date, request.end_date)
    elif request.start_date and not request.end_date:
        start_dt = request.start_date
        end_dt = date.today()
    elif request.end_date and not request.start_date:
        end_dt = request.end_date
        start_dt = end_dt - timedelta(days=days)
    else:
        end_dt = date.today()
        start_dt = end_dt - timedelta(days=days)

    lookback_date = start_dt.isoformat()
    end_date = end_dt.isoformat()
    date_window_text = f"between {lookback_date} and {end_date}"

    search_queries = _build_intel_search_queries(physician, date_window_text)
    ddg_timelimit = _ddg_timelimit_for_window(start_dt, end_dt)
    news_tl = _ddg_news_timelimit(ddg_timelimit)

    search_results: list[dict] = []
    for q in search_queries:
        hits = _run_web_search(q, max_results=4, timelimit=ddg_timelimit)
        search_results.append({"query": q, "results": hits})

    all_hits: list[dict] = []
    for s in search_results:
        for r in s["results"]:
            h = _hit_from_search_row(r, "web")
            if h:
                all_hits.append(h)

    for q in _build_tempus_source_queries(physician, date_window_text):
        for r in _run_web_search(q, max_results=3, timelimit=ddg_timelimit):
            h = _hit_from_search_row(r, "web")
            if h:
                all_hits.append(h)

    for q in _build_news_queries(physician):
        for r in _run_ddgs_news(q, max_results=3, timelimit=news_tl):
            h = _hit_from_search_row(r, "ddgs_news")
            if h:
                all_hits.append(h)

    news_api_key = (os.environ.get("NEWS_API_KEY") or "").strip()
    if news_api_key:
        cancer = physician.get("primary_cancer_focus") or "oncology"
        for q in (
            f"FDA {cancer} oncology approval",
            f"Tempus {cancer} genomic",
        ):
            for r in _run_newsapi_everything(
                news_api_key, q, start_dt, end_dt, page_size=8
            ):
                h = _hit_from_search_row(r, "newsapi")
                if h:
                    all_hits.append(h)

    all_hits = _dedupe_hits_by_url(all_hits)

    # Keep date-filtered results when we can parse a concrete date;
    # keep undated items so we don't over-prune useful sources.
    filtered_hits: list[dict] = []
    for h in all_hits:
        parsed = _parse_result_date(str(h.get("date") or "")) or _parse_result_date(
            f"{h.get('title', '')} {h.get('body', '')}"
        )
        if parsed is None or (start_dt <= parsed <= end_dt):
            filtered_hits.append(h)
    if filtered_hits:
        all_hits = filtered_hits

    boost_terms = _boost_terms_from_physician(physician)
    for h in all_hits:
        h["_rel_score"] = _score_hit_relevance(h, physician, boost_terms)
    all_hits.sort(key=lambda x: x.get("_rel_score", 0.0), reverse=True)
    all_hits = all_hits[:28]
    for h in all_hits:
        h.pop("_rel_score", None)
        h.pop("_origin", None)
    raw_text = "\n".join(
        f"[{i}] {h['title']}: {h['body']}"
        for i, h in enumerate(all_hits, start=1)
    )

    interests_line = physician.get("interests_from_crm") or "Not recorded"
    tags_line = physician.get("objection_tags") or "Not tagged"

    prompt = f"""You are preparing a pre-call intel digest for a Tempus sales rep who will meet {physician['name']}, a {physician['specialty']} at {physician['institution']} ({physician.get('city', '')}, {physician.get('state', '')}).

Account context (use this to judge relevance):
- Primary cancer focus: {physician['primary_cancer_focus']}
- Canonical objection tags from CRM: {tags_line}
- Stated objections (verbatim): {physician['objections_from_crm']}
- Interests / hooks from CRM: {interests_line[:1200]}
- Last CRM contact: {physician['last_contact_date'] or 'Unknown'}

Search results below mix web pages and news articles (when available), pre-ranked for topical overlap with this account. Each line is [N] title: snippet.
You MUST base every bullet on a specific [N] via source_index. Do not invent studies, approvals, or URLs.

Search results:
{raw_text[:12000]}

Date window: prioritize items whose implied date falls within {date_window_text}. If the snippet has no date, you may still use it if highly relevant; set date to empty string if unknown.

Return JSON only:
{{
  "drug_updates": [{{"headline": "...", "detail": "...", "relevance": "...", "source_index": 1, "date": "YYYY-MM-DD"}}],
  "publications": [{{"headline": "...", "detail": "...", "relevance": "...", "source_index": 2, "date": "..."}}],
  "tempus_updates": [{{"headline": "...", "detail": "...", "relevance": "...", "source_index": 3, "date": "..."}}],
  "competitive_intel": [{{"headline": "...", "detail": "...", "relevance": "...", "source_index": 4, "date": "..."}}]
}}

Section rules:
- drug_updates: FDA/regulatory or new therapy approvals relevant to {physician['primary_cancer_focus']} or closely related solid tumors. Skip if no matching [N].
- publications: ONLY if the cited snippet clearly refers to this physician's last name ({_last_name_from_display_name(physician['name'])}) OR their institution OR a paper clearly in their specialty + cancer focus. Otherwise return [].
- tempus_updates: ONLY items whose source [N] is Tempus-attributable: the snippet title/body OR URL must mention the company Tempus (word "Tempus") OR the URL must be on tempus.com or tempus.ai. Do NOT use generic oncology, FDA, or competitor stories that never mention Tempus. If no [N] qualifies, return [].
- competitive_intel: Foundation, Guardant, or other lab competitors only when the snippet discusses comprehensive genomic testing, liquid biopsy, or reimbursement in {physician['primary_cancer_focus']}.

For every non-empty item:
- "relevance" must be 1–2 sentences explaining why THIS matters for THIS call — reference specialty, cancer focus, objection tags, or interests. Generic filler is not allowed.
- source_index must point to the [N] you used.

If a section has no qualifying source, return an empty array for that section.
Only use source_index values that exist in the search results (1–{len(all_hits)}).
"""

    hits_by_index = {i: h for i, h in enumerate(all_hits, start=1)}

    try:
        raw = _call_llm_for_brief(prompt)
    except Exception:
        raw = {
            "drug_updates": [],
            "publications": [],
            "tempus_updates": [],
            "competitive_intel": [],
        }
    else:
        # Enforce the requested date window post-generation for items with explicit dates.
        raw["drug_updates"] = _filter_intel_items_by_date_window(
            raw.get("drug_updates", []), start_dt, end_dt, hits_by_index
        )
        raw["publications"] = _filter_intel_items_by_date_window(
            raw.get("publications", []), start_dt, end_dt, hits_by_index
        )
        raw["tempus_updates"] = _filter_tempus_items_to_qualified_sources(
            _filter_intel_items_by_date_window(
                raw.get("tempus_updates", []), start_dt, end_dt, hits_by_index
            ),
            hits_by_index,
        )
        raw["competitive_intel"] = _filter_intel_items_by_date_window(
            raw.get("competitive_intel", []), start_dt, end_dt, hits_by_index
        )

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
                rel = str(x.get("relevance", "")).strip()
                if len(rel) < 25:
                    continue
                hit = hits_by_index.get(idx_int) if idx_int is not None else None
                merged_date = _display_date_for_hit(hit, str(x.get("date", "")))
                out.append(
                    IntelItem(
                        headline=str(x.get("headline", ""))[:200],
                        detail=str(x.get("detail", ""))[:800],
                        relevance=rel[:400],
                        source_url=(raw_url or "")[:500],
                        date=merged_date,
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
        search_window_start=start_dt.isoformat(),
        search_window_end=end_dt.isoformat(),
        drug_updates=to_items(raw.get("drug_updates", []), url_by_index),
        publications=to_items(raw.get("publications", []), url_by_index),
        tempus_updates=to_items(raw.get("tempus_updates", []), url_by_index),
        competitive_intel=to_items(raw.get("competitive_intel", []), url_by_index),
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
