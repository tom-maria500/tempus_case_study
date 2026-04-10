"""RAG query logic and prompt construction for Tempus Sales Copilot."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

import chromadb
import pandas as pd
from dotenv import load_dotenv
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.schema import Document, NodeWithScore, TextNode
from llama_index.core.vector_stores import MetadataFilter, MetadataFilters, FilterOperator
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.anthropic import Anthropic
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.chroma import ChromaVectorStore

from models import BriefResponse, ChatRequest, ChatResponse, PhysicianProfile, ProviderRank
from priority_scoring import compute_base_score_series, row_effective_priority


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_CHROMA_DIR = BASE_DIR / "chroma_db"
CHROMA_COLLECTION_NAME = "tempus_physicians"

OBJECTION_TOPIC_KEYWORDS = {
    "turnaround_time": (
        "turnaround",
        "tat",
        "days",
        "first-line",
        "urgent",
        "delay",
    ),
    "cost_reimbursement": (
        "cost",
        "reimbursement",
        "coverage",
        "adlt",
        "medicare",
        "prior auth",
        "authorization",
        "financial",
        "appeal",
    ),
    "competitor_loyalty": (
        "foundation",
        "guardant",
        "vendor",
        "switch",
        "disruptive",
        "existing workflow",
        "loyal",
    ),
    "emr_integration": (
        "epic",
        "emr",
        "ehr",
        "structured field",
        "integration",
        "import",
        "portal",
    ),
    "staff_bandwidth": (
        "staff",
        "bandwidth",
        "workload",
        "coordinator",
        "sample prep",
        "shipping",
        "support team",
        "operations",
    ),
    "ai_skepticism": (
        "black box",
        "transparent",
        "transparency",
        "evidence",
        "citation",
        "validation",
        "raw data",
        "vcf",
        "trust",
        "ai-driven",
        "artificial intelligence",
    ),
}

KB_FACTS_BY_TOPIC = {
    "turnaround_time": (
        "xT CDx median turnaround time is 9-11 calendar days from sample receipt, and xF median turnaround is 7-9 days. "
        "Tempus reports >97% sample success for adequate FFPE, which reduces delays from recollection."
    ),
    "cost_reimbursement": (
        "xT CDx has CMS ADLT reimbursement at $4,500, and Tempus provides prior-authorization support through its billing team. "
        "Coverage details can be confirmed per plan to reduce staff burden around appeals and patient access."
    ),
    "competitor_loyalty": (
        "Tempus can support a phased switch with side-by-side report comparisons, rather than forcing an all-at-once migration. "
        "The platform unifies tissue (xT), liquid (xF), and RNA (xR) workflows to reduce multi-vendor fragmentation."
    ),
    "emr_integration": (
        "Tempus supports Epic integration with one-click result import and structured TMB/PD-L1 fields for charting. "
        "That helps teams avoid manual copy-paste and keeps documentation workflows consistent."
    ),
    "staff_bandwidth": (
        "Tempus provides pre-analytical guidance and support for ordering and specimen tracking to reduce coordinator burden. "
        "Sample success rates above 97% for adequate FFPE help minimize rework from failed specimens."
    ),
    "ai_skepticism": (
        "Tempus reporting is evidence-based with cited sources and access to underlying variant-level context when needed. "
        "Regulatory and validation anchors (including FDA-cleared components) support scientific trust and reviewability."
    ),
}


class PhysicianNotFoundError(Exception):
    """Raised when a physician cannot be located in market data."""


def _load_env() -> None:
    load_dotenv(override=False)


def _get_chroma_persist_dir() -> Path:
    env_path = os.getenv("CHROMA_PERSIST_DIR")
    return Path(env_path).resolve() if env_path else DEFAULT_CHROMA_DIR


def _init_vector_index() -> Tuple[VectorStoreIndex, ChromaVectorStore]:
    """Initialize LlamaIndex VectorStoreIndex backed by persistent Chroma."""
    _load_env()
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")

    chroma_client = chromadb.PersistentClient(path=str(_get_chroma_persist_dir()))
    collection = chroma_client.get_or_create_collection(CHROMA_COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=collection)

    # Load from persisted storage if available; otherwise construct lightweight index wrapper.
    llama_persist = _get_chroma_persist_dir() / "llama"
    if llama_persist.exists():
        from llama_index.core import StorageContext, load_index_from_storage

        storage_context = StorageContext.from_defaults(
            vector_store=vector_store, persist_dir=str(llama_persist)
        )
        index = load_index_from_storage(storage_context)
    else:
        index = VectorStoreIndex([], vector_store=vector_store)
    return index, vector_store


def _get_llm():
    """Return preferred LLM: Anthropic Claude if available, else OpenAI GPT-4o."""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key:
        return Anthropic(model="claude-sonnet-4-20250514")
    return OpenAI(model="gpt-4o")


def _load_market_dataframe() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "market_data.csv")


def _normalize_name(name: str) -> str:
    """Normalize physician names for more robust matching.

    - Lowercase
    - Strip titles like 'Dr.' or 'Doctor'
    - Remove punctuation (commas, periods)
    - Collapse multiple spaces
    """
    if not isinstance(name, str):
        name = str(name)
    n = name.lower().strip()
    # Remove common title and suffix noise
    n = re.sub(r"\b(dr\.?|doctor)\b", "", n)
    n = re.sub(r"\bmd\b", "", n)
    # Remove punctuation
    n = re.sub(r"[^a-z\s]", " ", n)
    # Collapse whitespace
    n = re.sub(r"\s+", " ", n)
    return n.strip()


def _find_physician_row(
    df: pd.DataFrame, physician_name: Optional[str], physician_id: Optional[str] = None
) -> Optional[pd.Series]:
    """Find a physician row by id (preferred) or name, with tolerant normalization."""
    if "physician_id" in df.columns and physician_id:
        id_matches = df[df["physician_id"].astype(str) == str(physician_id)]
        if not id_matches.empty:
            return id_matches.iloc[0]

    if not physician_name or "name" not in df.columns:
        return None

    target_norm = _normalize_name(physician_name)
    df = df.copy()
    df["_norm_name"] = df["name"].apply(_normalize_name)
    matches = df[df["_norm_name"] == target_norm]

    if matches.empty:
        return None
    return matches.iloc[0]


def _row_to_profile(
    row: pd.Series,
    df: pd.DataFrame,
    base_series: pd.Series,
) -> PhysicianProfile:
    last_contact = row.get("last_contact_date")
    last_contact_str = None if (pd.isna(last_contact) or last_contact == "") else str(last_contact)
    return PhysicianProfile(
        physician_id=str(row["physician_id"]),
        name=str(row["name"]),
        specialty=str(row["specialty"]),
        institution=str(row["institution"]),
        city=str(row["city"]),
        state=str(row["state"]),
        estimated_annual_patients=int(row["estimated_annual_patients"]),
        current_tempus_user=bool(row["current_tempus_user"]),
        primary_cancer_focus=str(row["primary_cancer_focus"]),
        last_contact_date=last_contact_str,  # Pydantic will parse ISO date string
        priority_score=row_effective_priority(row, df, base_series),
    )


def _retrieve_crm_for_physician(
    index: VectorStoreIndex, physician_name: str, physician_id: Optional[str]
) -> List[NodeWithScore]:
    """Retrieve CRM notes nodes for this physician (strictly by physician_id)."""
    filter_list = [
        MetadataFilter(key="source", operator=FilterOperator.EQ, value="crm_notes"),
    ]
    if physician_id and str(physician_id).strip():
        filter_list.append(
            MetadataFilter(key="physician_id", operator=FilterOperator.EQ, value=str(physician_id))
        )
    filters = MetadataFilters(filters=filter_list)
    retriever = index.as_retriever(similarity_top_k=5, filters=filters)
    query = f"CRM history and objections for {physician_name}"
    if physician_id:
        query += f" {physician_id}"
    return retriever.retrieve(query)


def _retrieve_kb_chunks(
    index: VectorStoreIndex, specialty: str, primary_cancer_focus: str, known_objections: str
) -> List[NodeWithScore]:
    """Hybrid retrieval: dense + sparse keyword scoring + lightweight reranking."""
    query = (
        f"Tempus test portfolio, performance metrics, and objection handling relevant for "
        f"{specialty} and cancer types {primary_cancer_focus}. "
        f"Address objections: {known_objections}."
    )
    dense_nodes = _retrieve_kb_dense(index, query, top_k=10)
    sparse_nodes = _retrieve_kb_sparse(
        query=query,
        specialty=specialty,
        primary_cancer_focus=primary_cancer_focus,
        known_objections=known_objections,
        top_k=10,
    )
    return _rerank_hybrid_kb_nodes(
        query=query,
        dense_nodes=dense_nodes,
        sparse_nodes=sparse_nodes,
        top_k=5,
    )


def _tokenize_for_sparse(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _keyword_score(text: str, query_terms: List[str]) -> float:
    if not text or not query_terms:
        return 0.0
    lowered = text.lower()
    score = 0.0
    for term in query_terms:
        if len(term) <= 2:
            continue
        if re.search(r"\b" + re.escape(term) + r"\b", lowered):
            score += 1.0
    return score


def _kb_corpus_documents() -> List[Document]:
    path = DATA_DIR / "tempus_kb.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    docs: List[Document] = []
    current_h2: str | None = None
    current_h3: str | None = None
    lines: List[str] = []
    counter = 0

    def flush() -> None:
        nonlocal counter, lines
        if not current_h2 or not lines:
            return
        content = "\n".join(lines).strip()
        if not content:
            lines = []
            return
        counter += 1
        heading = current_h2 if not current_h3 else f"{current_h2} / {current_h3}"
        docs.append(
            Document(
                text=content,
                metadata={
                    "source": "knowledge_base",
                    "section": current_h2,
                    "subsection": current_h3 or "",
                },
                doc_id=f"kb-corpus-{counter}-{heading.lower().replace(' ', '-').replace('/', '-')}",
            )
        )
        lines = []

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            current_h2 = line[3:].strip()
            current_h3 = None
            continue
        if line.startswith("### "):
            flush()
            current_h3 = line[4:].strip()
            continue
        if current_h2 is not None:
            lines.append(line)
    flush()
    return docs


def _retrieve_kb_dense(index: VectorStoreIndex, query: str, top_k: int = 10) -> List[NodeWithScore]:
    filters = MetadataFilters(
        filters=[MetadataFilter(key="source", operator=FilterOperator.EQ, value="knowledge_base")]
    )
    retriever = index.as_retriever(similarity_top_k=top_k, filters=filters)
    return retriever.retrieve(query)


def _retrieve_kb_sparse(
    query: str,
    specialty: str,
    primary_cancer_focus: str,
    known_objections: str,
    top_k: int = 10,
) -> List[NodeWithScore]:
    query_terms = _tokenize_for_sparse(
        " ".join([query, specialty, primary_cancer_focus, known_objections])
    )
    scored: List[tuple[float, Document]] = []
    for doc in _kb_corpus_documents():
        text = doc.text
        score = _keyword_score(text, query_terms)
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)

    out: List[NodeWithScore] = []
    for score, doc in scored[:top_k]:
        node = TextNode(text=doc.text, metadata=doc.metadata)
        out.append(NodeWithScore(node=node, score=score))
    return out


def _rerank_hybrid_kb_nodes(
    query: str,
    dense_nodes: List[NodeWithScore],
    sparse_nodes: List[NodeWithScore],
    top_k: int = 5,
) -> List[NodeWithScore]:
    """Merge and rerank candidates with reciprocal-rank fusion + keyword match bonus."""
    merged: Dict[str, NodeWithScore] = {}
    dense_rank: Dict[str, int] = {}
    sparse_rank: Dict[str, int] = {}

    for i, n in enumerate(dense_nodes):
        key = n.node.get_content().strip()[:1200]
        dense_rank[key] = i + 1
        merged[key] = n
    for i, n in enumerate(sparse_nodes):
        key = n.node.get_content().strip()[:1200]
        sparse_rank[key] = i + 1
        if key not in merged:
            merged[key] = n

    query_terms = _tokenize_for_sparse(query)
    reranked: List[NodeWithScore] = []
    for key, node in merged.items():
        rr_dense = 1.0 / (60 + dense_rank.get(key, 10_000))
        rr_sparse = 1.0 / (60 + sparse_rank.get(key, 10_000))
        kw_bonus = 0.05 * _keyword_score(node.node.get_content(), query_terms)
        final_score = rr_dense + rr_sparse + kw_bonus
        reranked.append(NodeWithScore(node=node.node, score=final_score))
    reranked.sort(key=lambda n: n.score or 0.0, reverse=True)
    return reranked[:top_k]


def _extract_objections_from_crm_nodes(crm_nodes: List[NodeWithScore]) -> List[str]:
    """Prefer full OBJECTIONS block from summary/objections docs; skip per-topic shards."""
    objections: List[str] = []
    seen: set[str] = set()
    preferred_types = frozenset({"crm_summary", "crm_objections"})
    for node in crm_nodes:
        try:
            doc_type = str(node.node.metadata.get("doc_type") or "")  # type: ignore[attr-defined]
            meta_obj = node.node.metadata.get("objections")  # type: ignore[attr-defined]
        except Exception:
            doc_type = ""
            meta_obj = None
        if doc_type and doc_type not in preferred_types:
            continue
        if meta_obj:
            val = str(meta_obj).strip()
            if val and val not in seen:
                seen.add(val)
                objections.append(val)
    if not objections:
        for node in crm_nodes:
            try:
                meta_obj = node.node.metadata.get("objections")  # type: ignore[attr-defined]
            except Exception:
                meta_obj = None
            if meta_obj:
                val = str(meta_obj).strip()
                if val and val not in seen:
                    seen.add(val)
                    objections.append(val)
    return objections


def _extract_objection_tags_from_crm_nodes(crm_nodes: List[NodeWithScore]) -> List[str]:
    """Read comma-separated OBJECTION_TAGS from CRM metadata (prefer summary doc)."""
    preferred: List[NodeWithScore] = []
    rest: List[NodeWithScore] = []
    for node in crm_nodes:
        try:
            dt = str(node.node.metadata.get("doc_type") or "")  # type: ignore[attr-defined]
        except Exception:
            dt = ""
        if dt == "crm_summary":
            preferred.append(node)
        else:
            rest.append(node)
    for node in preferred + rest:
        try:
            raw = node.node.metadata.get("objection_tags")  # type: ignore[attr-defined]
        except Exception:
            raw = None
        if raw and str(raw).strip():
            return [t.strip() for t in str(raw).split(",") if t.strip()]
    return []


def _canonical_topics_from_tags(tags: List[str]) -> List[str]:
    """Keep only tags that match known RAG objection topic keys."""
    out: List[str] = []
    for t in tags:
        key = t.strip().lower().replace(" ", "_")
        if key in OBJECTION_TOPIC_KEYWORDS and key not in out:
            out.append(key)
    return out


def _infer_objection_topics(text: str) -> set[str]:
    lowered = (text or "").lower()
    topics: set[str] = set()
    for topic, keywords in OBJECTION_TOPIC_KEYWORDS.items():
        if any(_keyword_in_text(lowered, kw) for kw in keywords):
            topics.add(topic)
    return topics


def _keyword_in_text(text: str, keyword: str) -> bool:
    # Word-boundary matching avoids false positives like matching "ai" inside "raised".
    pattern = r"\b" + re.escape(keyword).replace(r"\ ", r"\s+") + r"\b"
    return re.search(pattern, text) is not None


def _select_primary_topics(objections: List[str], max_topics: int = 2) -> set[str]:
    """Pick the first 1-2 objection topics in CRM order to keep handlers focused."""
    ordered: List[str] = []
    for objection in objections:
        lowered = (objection or "").lower()
        first_pos: List[tuple[int, str]] = []
        for topic, keywords in OBJECTION_TOPIC_KEYWORDS.items():
            positions = []
            for kw in keywords:
                pattern = r"\b" + re.escape(kw).replace(r"\ ", r"\s+") + r"\b"
                m = re.search(pattern, lowered)
                if m:
                    positions.append(m.start())
            if positions:
                first_pos.append((min(positions), topic))
        for _, topic in sorted(first_pos, key=lambda x: x[0]):
            if topic not in ordered:
                ordered.append(topic)
    return set(ordered[:max_topics])


def _handler_matches_required_topics(
    handler: str,
    required_topics: set[str],
    allowed_topics: set[str] | None = None,
) -> bool:
    if not required_topics:
        return bool(handler.strip())
    handler_topics = _infer_objection_topics(handler)
    if not required_topics.issubset(handler_topics):
        return False
    if allowed_topics is not None and not handler_topics.issubset(allowed_topics):
        return False
    return True


def _fallback_objection_handler(required_topics: set[str], raw_objections: List[str]) -> str:
    if not required_topics:
        return (
            "Acknowledge the physician's top concern directly, then answer it with one concrete Tempus metric from the knowledge base. "
            "Close by proposing a low-friction next step tailored to their workflow."
        )
    concern_labels = {
        "turnaround_time": "turnaround time",
        "cost_reimbursement": "cost and reimbursement",
        "competitor_loyalty": "vendor switching risk",
        "emr_integration": "EMR workflow fit",
        "staff_bandwidth": "staff bandwidth",
        "ai_skepticism": "AI transparency",
    }
    concern_phrase = ", ".join(concern_labels.get(t, t) for t in sorted(required_topics))
    topic_facts = [KB_FACTS_BY_TOPIC[t] for t in sorted(required_topics) if t in KB_FACTS_BY_TOPIC]
    topic_text = " ".join(topic_facts).strip()
    return f"I hear your concerns around {concern_phrase}. {topic_text}"


def _rewrite_objection_handler_strict(
    objection_handler: str,
    required_topics: set[str],
    allowed_topics: set[str],
    raw_objections: List[str],
    kb_chunks: List[str],
) -> str:
    if not required_topics:
        return objection_handler.strip()
    topics_list = ", ".join(sorted(required_topics))
    objections_text = "\n".join(f"- {x}" for x in raw_objections if x.strip()) or "- None provided"
    kb_text = "\n\n---\n\n".join(kb_chunks[:4])
    rewrite_prompt = f"""
You are fixing an objection handler that drifted away from the physician's actual objections.

Required objection topics (must all be addressed): {topics_list}
Allowed objection topics (do not introduce others): {", ".join(sorted(allowed_topics))}
Original objections from CRM:
{objections_text}

Current objection handler (may be wrong):
{objection_handler}

Product knowledge:
{kb_text}

Return JSON only:
{{
  "objection_handler": "<2-3 sentences, must address required topics and avoid any topic outside allowed topics using only facts above>"
}}
"""
    raw = _call_llm_for_brief(rewrite_prompt)
    rewritten = str(raw.get("objection_handler", "")).strip()
    if rewritten and _handler_matches_required_topics(
        rewritten, required_topics, allowed_topics=allowed_topics
    ):
        return rewritten
    return _fallback_objection_handler(required_topics, raw_objections)


def _build_prompt(
    physician_profile: PhysicianProfile,
    crm_nodes: List[NodeWithScore],
    kb_nodes: List[NodeWithScore],
) -> Tuple[str, List[str], List[str], set[str]]:
    """Construct structured prompt and return (prompt, kb_chunks_text)."""
    # Physician context
    ctx = physician_profile
    physician_context = (
        f"Name: {ctx.name}\n"
        f"Physician ID: {ctx.physician_id}\n"
        f"Specialty: {ctx.specialty}\n"
        f"Institution: {ctx.institution}\n"
        f"Location: {ctx.city}, {ctx.state}\n"
        f"Estimated annual oncology patients: {ctx.estimated_annual_patients}\n"
        f"Primary cancer focus: {ctx.primary_cancer_focus}\n"
        f"Current Tempus user: {ctx.current_tempus_user}\n"
        f"Last contact date: {ctx.last_contact_date}\n"
        f"Priority score (0-10): {ctx.priority_score}\n"
    )

    # CRM history
    if crm_nodes:
        crm_text = "\n\n".join(node.node.get_content() for node in crm_nodes)
    else:
        crm_text = "No prior CRM notes available for this physician. Treat as cold outreach."

    # Extract objections from CRM metadata (same OBJECTIONS field as in CRM HISTORY text)
    # so the model can tie the objection_handler to the data.
    objections_from_crm = _extract_objections_from_crm_nodes(crm_nodes)
    tags_canonical = _canonical_topics_from_tags(_extract_objection_tags_from_crm_nodes(crm_nodes))
    if tags_canonical:
        required_topics = set(tags_canonical[:2])
        all_detected_topics = set(tags_canonical)
    else:
        all_detected_topics = _infer_objection_topics("\n".join(objections_from_crm))
        required_topics = _select_primary_topics(objections_from_crm, max_topics=2)
        if not required_topics:
            required_topics = all_detected_topics

    objections_text = (
        "None in CRM HISTORY for this physician; choose one relevant theme from "
        "PRODUCT KNOWLEDGE 'Facts by Objection Topic' (e.g. cost, vendor loyalty, EMR, "
        "AI transparency, staff bandwidth) and respond using KB metrics."
        if not objections_from_crm
        else "\n".join(f"- {obj}" for obj in objections_from_crm)
    )

    # KB chunks
    kb_chunks: List[str] = []
    for node in kb_nodes:
        kb_chunks.append(node.node.get_content())
    kb_text = "\n\n---\n\n".join(kb_chunks)

    instructions = """
You are a Tempus oncology sales copilot. Generate a JSON object with the following EXACT shape:

{
  "meeting_script": "<string>",
  "objection_handler": "<string>",
  "priority_rationale": "<string>"
}

Use the same CRM data throughout. [CRM HISTORY] contains this physician's REP_NOTES, OBJECTIONS, and INTERESTS.
The section [OBJECTIONS FROM CRM HISTORY] below is the OBJECTIONS field from that same CRM data (for reference).
Ground your output in that data so the script and objection handler reflect this physician's situation.

Field requirements:
- "meeting_script": 80–100 words. 30-second elevator pitch.
  - Base it on this physician's cancer focus, INTERESTS, and REP_NOTES from [CRM HISTORY].
  - Mention only Tempus tests in PRODUCT KNOWLEDGE (e.g., xT, xF, xR, xE).
  - If [CRM HISTORY] says no prior notes, treat as cold outreach.
- "objection_handler": 2–3 sentences.
  - Address the objection(s) in [OBJECTIONS FROM CRM HISTORY]. Your response must match the concern(s) raised there — use PRODUCT KNOWLEDGE to respond to whatever theme or themes appear. Do not substitute a different concern or default to a single theme. Restate their concern, then respond with concrete metrics from PRODUCT KNOWLEDGE only.
- "priority_rationale": 1–2 sentences. Generate from physician context: volume, Tempus usage, priority_score. Do not copy from CRM — derive this yourself from [PHYSICIAN CONTEXT].

Rules:
- Only use metrics and tests from PRODUCT KNOWLEDGE.
- Do NOT mention TAT or Epic unless it appears in [OBJECTIONS FROM CRM HISTORY] or [CRM HISTORY].
- Objection handler must reflect the objections in [OBJECTIONS FROM CRM HISTORY]. Vary the handler by what is stated there; do not use the same response for every physician.
- Objection handler must explicitly cover every topic listed in [REQUIRED OBJECTION TOPICS] and avoid introducing unrelated themes.
- Keep the objection handler tightly focused: address only the required objection topics and do not add extra concern themes.
- Tone: professional, peer-to-peer.
- Respond ONLY with valid JSON, no extra text.
"""

    tags_line = (
        ", ".join(tags_canonical) if tags_canonical else "none (infer from OBJECTIONS text)"
    )
    prompt = (
        "[PHYSICIAN CONTEXT]\n"
        f"{physician_context}\n\n"
        "[CRM HISTORY]\n"
        f"{crm_text}\n\n"
        "[CANONICAL OBJECTION TAGS FROM CRM]\n"
        f"{tags_line}\n\n"
        "[OBJECTIONS FROM CRM HISTORY]\n"
        f"{objections_text}\n\n"
        "[REQUIRED OBJECTION TOPICS]\n"
        f"{', '.join(sorted(required_topics)) if required_topics else 'none'}\n\n"
        "[PRODUCT KNOWLEDGE]\n"
        f"{kb_text}\n\n"
        "[INSTRUCTIONS]\n"
        f"{instructions.strip()}\n"
    )

    return prompt, kb_chunks, objections_from_crm, required_topics, all_detected_topics


def _call_llm_for_brief(prompt: str) -> dict:
    """Call LLM and return parsed JSON dict."""
    llm = _get_llm()
    start = time.time()
    try:
        response = llm.complete(prompt)
        text = str(response).strip()

        # In case model wraps JSON in code fences or extra text, try to extract JSON substring.
        if "```" in text:
            first = text.find("```")
            last = text.rfind("```")
            if last > first:
                inner = text[first + 3 : last].strip()
                if inner.lower().startswith("json"):
                    inner = inner[4:].strip()
                text = inner

        try:
            parsed = json.loads(text)
        except ValueError:
            # Fallback: attempt to extract the first {...} block as JSON.
            start_json = text.find("{")
            end_json = text.rfind("}")
            if start_json != -1 and end_json != -1 and end_json > start_json:
                candidate = text[start_json : end_json + 1]
                parsed = json.loads(candidate)
            else:
                # If we cannot salvage valid JSON, fall back to empty dict.
                parsed = {}

        # Ensure callers always receive a dict so .get(...) calls are safe.
        if not isinstance(parsed, dict):
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                parsed = parsed[0]
            else:
                parsed = {}
    finally:
        duration_ms = int((time.time() - start) * 1000)
        # Log physician not included here; caller can add context if desired.
        print(f"[rag] LLM call completed in {duration_ms} ms")
    return parsed


def generate_physician_brief(
    physician_name: str, physician_id: Optional[str] = None
) -> BriefResponse:
    """Primary RAG entrypoint: generate structured brief for a physician."""
    index, _ = _init_vector_index()
    df = _load_market_dataframe()
    row = _find_physician_row(df, physician_name, physician_id)
    if row is None:
        raise PhysicianNotFoundError(f"Physician '{physician_name}' not found")

    base_series = compute_base_score_series(df)
    profile = _row_to_profile(row, df, base_series)

    # Retrieve CRM and KB
    crm_nodes = _retrieve_crm_for_physician(index, profile.name, profile.physician_id)

    # Extract objection snippets from CRM metadata only, so retrieval and the
    # objection handler are grounded on the physician's *actual* concerns
    # (e.g., cost, existing vendor, AI skepticism) rather than generic text.
    known_objections_list = _extract_objections_from_crm_nodes(crm_nodes)
    known_objections = "\n".join(known_objections_list)

    kb_nodes = _retrieve_kb_chunks(
        index,
        specialty=profile.specialty,
        primary_cancer_focus=profile.primary_cancer_focus,
        known_objections=known_objections,
    )

    prompt, kb_chunks, crm_objections, required_topics, all_detected_topics = _build_prompt(
        profile, crm_nodes, kb_nodes
    )
    raw = _call_llm_for_brief(prompt)

    meeting_script = str(raw.get("meeting_script", "")).strip()
    objection_handler = str(raw.get("objection_handler", "")).strip()
    priority_rationale = str(raw.get("priority_rationale", "")).strip()
    allowed_topics = required_topics if required_topics else all_detected_topics
    if not _handler_matches_required_topics(
        objection_handler,
        required_topics,
        allowed_topics=allowed_topics,
    ):
        objection_handler = _rewrite_objection_handler_strict(
            objection_handler=objection_handler,
            required_topics=required_topics,
            allowed_topics=allowed_topics,
            raw_objections=crm_objections,
            kb_chunks=kb_chunks,
        )

    return BriefResponse(
        physician=profile,
        meeting_script=meeting_script,
        objection_handler=objection_handler,
        priority_rationale=priority_rationale,
        retrieved_kb_chunks=kb_chunks,
    )


def process_chat(request: ChatRequest) -> ChatResponse:
    """Coach the rep using brief context and conversation history."""
    df = _load_market_dataframe()
    row = _find_physician_row(df, None, request.physician_id)
    if row is None:
        raise PhysicianNotFoundError(f"Physician '{request.physician_id}' not found")

    physician_name = str(row["name"])
    specialty = str(row["specialty"])
    institution = str(row["institution"])

    ctx = request.brief_context
    meeting_script = ctx.get("meeting_script", "") or ""
    objection_handler = ctx.get("objection_handler", "") or ""
    kb_chunks = ctx.get("retrieved_kb_chunks") or []
    kb_text = "\n\n".join(kb_chunks) if kb_chunks else "No KB chunks provided."
    allowed_topics = _infer_objection_topics(objection_handler)

    system_prompt = f"""You are a sales coach helping a Tempus sales rep prep for a physician meeting.
You have access to the rep's generated brief and the Tempus knowledge base.

Physician: {physician_name} | {specialty} | {institution}

Brief generated:

Meeting script: {meeting_script}

Objection handler: {objection_handler}

Relevant product facts:
{kb_text}

Rules:
- Coach the rep, don't speak to the physician directly
- Only cite metrics and product names from the knowledge base above
- Keep responses short and actionable — reps are prepping fast
- If asked to rewrite the script, keep it personalized to this physician
- Stay anchored to the objection themes in the objection handler; do not introduce unrelated objection themes.
- Tone: confident, direct, like a senior rep coaching a junior one

Respond with a JSON object with exactly two keys:
- "response": your coaching answer (string)
- "suggested_followups": array of 3 short follow-up question strings
"""

    # Cap conversation history at 10 messages
    history = request.conversation_history[-10:]
    messages_text = "\n".join(
        f"{m.role.upper()}: {m.content}" for m in history
    )

    user_prompt = f"""{messages_text}

USER: {request.message}

Respond with JSON only:
{{"response": "...", "suggested_followups": ["...", "...", "..."]}}
"""

    full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
    raw = _call_llm_for_brief(full_prompt)

    response_text = str(raw.get("response", "")).strip()
    if allowed_topics and not _infer_objection_topics(response_text).issubset(allowed_topics):
        # One strict retry before returning to reduce topic drift in coaching.
        strict_retry_prompt = (
            f"{full_prompt}\n\n"
            f"IMPORTANT RETRY RULE: Only discuss these objection topics: {', '.join(sorted(allowed_topics))}. "
            "If needed, answer by focusing on these topics and do not introduce other concerns."
        )
        retried = _call_llm_for_brief(strict_retry_prompt)
        retry_text = str(retried.get('response', '')).strip()
        if retry_text:
            response_text = retry_text
    suggested = raw.get("suggested_followups")
    if isinstance(suggested, list):
        suggested = [str(s).strip() for s in suggested[:3]]
    else:
        suggested = []

    return ChatResponse(response=response_text, suggested_followups=suggested)


def get_ranked_providers(city: Optional[str] = None, limit: int = 10) -> List[ProviderRank]:
    """Return top N providers by effective priority (formula + adjustment), optional city filter."""
    df = _load_market_dataframe()
    if "priority_adjustment" not in df.columns:
        df["priority_adjustment"] = 0.0
    base_series = compute_base_score_series(df)
    df = df.copy()
    df["_effective"] = df.apply(lambda r: row_effective_priority(r, df, base_series), axis=1)
    if city:
        df = df[df["city"].str.lower() == city.lower()]
    df = df.sort_values("_effective", ascending=False).head(limit)

    providers: List[ProviderRank] = []
    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        providers.append(
            ProviderRank(
                physician_id=str(row["physician_id"]),
                name=str(row["name"]),
                institution=str(row["institution"]),
                specialty=str(row["specialty"]),
                estimated_annual_patients=int(row["estimated_annual_patients"]),
                priority_score=float(row["_effective"]),
                primary_cancer_focus=str(row["primary_cancer_focus"]),
                current_tempus_user=bool(row["current_tempus_user"]),
                last_contact_date=None
                if (pd.isna(row.get("last_contact_date")) or row.get("last_contact_date") == "")
                else str(row.get("last_contact_date")),
                rank=rank,
            )
        )
    return providers


