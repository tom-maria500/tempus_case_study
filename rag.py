"""RAG query logic and prompt construction for Tempus Sales Copilot."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import List, Optional, Tuple
import re

import chromadb
import pandas as pd
from dotenv import load_dotenv
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.schema import Document, NodeWithScore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.anthropic import Anthropic
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.chroma import ChromaVectorStore

from models import BriefResponse, ChatRequest, ChatResponse, PhysicianProfile, ProviderRank


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_CHROMA_DIR = BASE_DIR / "chroma_db"
CHROMA_COLLECTION_NAME = "tempus_physicians"


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


def _row_to_profile(row: pd.Series) -> PhysicianProfile:
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
        priority_score=float(row["priority_score"]),
    )


def _retrieve_crm_for_physician(
    index: VectorStoreIndex, physician_name: str, physician_id: Optional[str]
) -> List[NodeWithScore]:
    """Retrieve CRM notes nodes for this physician (by metadata filter + text)."""
    retriever = index.as_retriever(similarity_top_k=3)
    # Use a query that combines name and optional id for better match.
    query = f"CRM history and objections for {physician_name}"
    if physician_id:
        query += f" ({physician_id})"
    nodes = retriever.retrieve(query)
    # Filter down to CRM sources if metadata available
    filtered = [
        n for n in nodes if n.node.metadata.get("source") == "crm_notes"  # type: ignore[attr-defined]
    ]
    return filtered or nodes


def _retrieve_kb_chunks(
    index: VectorStoreIndex, specialty: str, primary_cancer_focus: str, known_objections: str
) -> List[NodeWithScore]:
    """Retrieve relevant KB chunks based on specialty and objections."""
    retriever = index.as_retriever(similarity_top_k=3)
    query = (
        f"Tempus test portfolio, performance metrics, and objection handling relevant for "
        f"{specialty} and cancer types {primary_cancer_focus}. "
        f"Address objections: {known_objections}."
    )
    return retriever.retrieve(query)


def _build_prompt(
    physician_profile: PhysicianProfile,
    crm_nodes: List[NodeWithScore],
    kb_nodes: List[NodeWithScore],
) -> Tuple[str, List[str]]:
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
    objections_from_crm: List[str] = []
    for node in crm_nodes:
        try:
            meta_obj = node.node.metadata.get("objections")  # type: ignore[attr-defined]
        except Exception:
            meta_obj = None
        if meta_obj:
            objections_from_crm.append(str(meta_obj))

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
  - Address the objection(s) listed in [OBJECTIONS FROM CRM HISTORY] (i.e. the OBJECTIONS from the CRM data above).
  - First restate their concern, then respond with concrete metrics from PRODUCT KNOWLEDGE only.
- "priority_rationale": 1–2 sentences. Volume, Tempus usage, priority_score.

Rules:
- Only use metrics and tests from PRODUCT KNOWLEDGE.
- Do NOT mention TAT or Epic unless it appears in [OBJECTIONS FROM CRM HISTORY] or [CRM HISTORY].
- Tone: professional, peer-to-peer.
- Respond ONLY with valid JSON, no extra text.
"""

    prompt = (
        "[PHYSICIAN CONTEXT]\n"
        f"{physician_context}\n\n"
        "[CRM HISTORY]\n"
        f"{crm_text}\n\n"
        "[OBJECTIONS FROM CRM HISTORY]\n"
        f"{objections_text}\n\n"
        "[PRODUCT KNOWLEDGE]\n"
        f"{kb_text}\n\n"
        "[INSTRUCTIONS]\n"
        f"{instructions.strip()}\n"
    )

    return prompt, kb_chunks


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

    profile = _row_to_profile(row)

    # Retrieve CRM and KB
    crm_nodes = _retrieve_crm_for_physician(index, profile.name, profile.physician_id)

    # Extract objection snippets from CRM metadata only, so retrieval and the
    # objection handler are grounded on the physician's *actual* concerns
    # (e.g., cost, existing vendor, AI skepticism) rather than generic text.
    known_objections_list: List[str] = []
    for node in crm_nodes:
        try:
            meta_obj = node.node.metadata.get("objections")  # type: ignore[attr-defined]
        except Exception:
            meta_obj = None
        if meta_obj:
            known_objections_list.append(str(meta_obj))
    known_objections = "\n".join(known_objections_list)

    kb_nodes = _retrieve_kb_chunks(
        index,
        specialty=profile.specialty,
        primary_cancer_focus=profile.primary_cancer_focus,
        known_objections=known_objections,
    )

    prompt, kb_chunks = _build_prompt(profile, crm_nodes, kb_nodes)
    raw = _call_llm_for_brief(prompt)

    meeting_script = str(raw.get("meeting_script", "")).strip()
    objection_handler = str(raw.get("objection_handler", "")).strip()
    priority_rationale = str(raw.get("priority_rationale", "")).strip()

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
    suggested = raw.get("suggested_followups")
    if isinstance(suggested, list):
        suggested = [str(s).strip() for s in suggested[:3]]
    else:
        suggested = []

    return ChatResponse(response=response_text, suggested_followups=suggested)


def get_ranked_providers(city: Optional[str] = None, limit: int = 10) -> List[ProviderRank]:
    """Return top N providers by priority_score, optionally filtered by city."""
    df = _load_market_dataframe()
    if city:
        df = df[df["city"].str.lower() == city.lower()]
    df = df.sort_values("priority_score", ascending=False).head(limit)

    providers: List[ProviderRank] = []
    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        providers.append(
            ProviderRank(
                physician_id=str(row["physician_id"]),
                name=str(row["name"]),
                institution=str(row["institution"]),
                specialty=str(row["specialty"]),
                estimated_annual_patients=int(row["estimated_annual_patients"]),
                priority_score=float(row["priority_score"]),
                primary_cancer_focus=str(row["primary_cancer_focus"]),
                current_tempus_user=bool(row["current_tempus_user"]),
                last_contact_date=None
                if (pd.isna(row.get("last_contact_date")) or row.get("last_contact_date") == "")
                else str(row.get("last_contact_date")),
                rank=rank,
            )
        )
    return providers


