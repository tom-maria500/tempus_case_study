"""Data ingestion and ChromaDB indexing for Tempus Sales Copilot.

This script:
- Loads market_data.csv into Documents with physician metadata.
- Parses crm_notes.txt into Documents keyed by physician.
- Chunks tempus_kb.md by section into knowledge base Documents.
- Indexes everything into a persistent ChromaDB vector store using
  OpenAI text-embedding-3-small via LlamaIndex.

Run:
    python ingest.py            # build index if it does not exist
    python ingest.py --force    # rebuild index from scratch
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Dict, List

import chromadb
import pandas as pd
from dotenv import load_dotenv
from llama_index.core import Document, Settings, VectorStoreIndex
from priority_scoring import compute_base_score_series, row_effective_priority
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_CHROMA_DIR = BASE_DIR / "chroma_db"
CHROMA_COLLECTION_NAME = "tempus_physicians"


def _load_env() -> None:
    """Load environment variables from .env if present."""
    load_dotenv(override=False)


def _get_chroma_persist_dir() -> Path:
    env_path = os.getenv("CHROMA_PERSIST_DIR")
    return Path(env_path).resolve() if env_path else DEFAULT_CHROMA_DIR


def _index_exists(persist_dir: Path) -> bool:
    """Check if a ChromaDB directory already exists."""
    # For Chroma, existence of directory is enough to treat as existing index.
    return persist_dir.exists() and any(persist_dir.iterdir())


def _load_market_data() -> List[Document]:
    """Load market_data.csv and convert each row to a Document."""
    csv_path = DATA_DIR / "market_data.csv"
    df = pd.read_csv(csv_path)
    if "priority_adjustment" not in df.columns:
        df["priority_adjustment"] = 0.0
    base_series = compute_base_score_series(df)

    docs: List[Document] = []
    for _, row in df.iterrows():
        physician_id = str(row["physician_id"])
        effective_priority = row_effective_priority(row, df, base_series)
        text = (
            f"Physician market data for {row['name']} ({row['physician_id']}): "
            f"specialty={row['specialty']}, institution={row['institution']}, "
            f"city={row['city']}, state={row['state']}, "
            f"estimated_annual_patients={row['estimated_annual_patients']}, "
            f"primary_cancer_focus={row['primary_cancer_focus']}, "
            f"current_tempus_user={row['current_tempus_user']}, "
            f"last_contact_date={row['last_contact_date']}, "
            f"priority_score={effective_priority}."
        )
        metadata = {
            "source": "market_data",
            "physician_id": physician_id,
            "name": row["name"],
            "specialty": row["specialty"],
            "institution": row["institution"],
            "city": row["city"],
            "state": row["state"],
            "estimated_annual_patients": int(row["estimated_annual_patients"]),
            "current_tempus_user": bool(row["current_tempus_user"]),
            "primary_cancer_focus": row["primary_cancer_focus"],
            "last_contact_date": (
                None if pd.isna(row["last_contact_date"]) else str(row["last_contact_date"])
            ),
            "priority_score": float(effective_priority),
        }
        docs.append(Document(text=text, metadata=metadata, doc_id=f"market-{physician_id}"))

    return docs


# Lines like `PHYSICIAN:`, `OBJECTION_TAGS:`, `OBJECTIONS:` (multi-line supported).
_CRM_FIELD_HEADER = re.compile(r"^([A-Z][A-Z0-9_]*):\s*(.*)$")
_OBJ_BULLET = re.compile(r"^\s*-\s*\[([a-z0-9_]+)\]\s*(.*)$", re.IGNORECASE)


def _parse_objection_bullets(text: str) -> List[tuple[str, str]]:
    """Parse lines like '- [turnaround_time] Needs results in 10 days'."""
    out: List[tuple[str, str]] = []
    for line in (text or "").splitlines():
        m = _OBJ_BULLET.match(line.strip())
        if m:
            out.append((m.group(1).lower(), m.group(2).strip()))
    return out


def _parse_crm_block(block: str) -> Dict:
    """Parse a single CRM notes block into structured fields.

    Supports:
    - OBJECTION_TAGS: comma-separated canonical tags (aligns with RAG topic keys)
    - OBJECTIONS: multi-line; continuation lines do not start with KEY:
    - Standard single-line fields (DATE, REP_NOTES, INTERESTS, etc.)
    """
    lines = block.splitlines()
    data: Dict[str, str] = {}
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        m = _CRM_FIELD_HEADER.match(stripped)
        if not m:
            i += 1
            continue
        key = m.group(1).lower()
        val = m.group(2).strip()

        if key == "physician":
            rest = val
            if "|" in rest:
                name_part, id_part = [p.strip() for p in rest.split("|", 1)]
                data["name"] = name_part
                data["physician_id"] = id_part
            else:
                data["name"] = rest
            i += 1
            continue

        if key == "objections":
            parts: List[str] = []
            if val:
                parts.append(val)
            i += 1
            while i < len(lines):
                nxt = lines[i].strip()
                if not nxt:
                    i += 1
                    continue
                if _CRM_FIELD_HEADER.match(nxt):
                    break
                parts.append(nxt)
                i += 1
            data["objections"] = "\n".join(parts).strip()
            continue

        data[key] = val
        i += 1
    return data


def _load_crm_notes() -> List[Document]:
    """Load crm_notes.txt into Documents."""
    path = DATA_DIR / "crm_notes.txt"
    raw = path.read_text(encoding="utf-8")
    blocks = [b.strip() for b in raw.split("---") if b.strip()]

    docs: List[Document] = []
    for idx, block in enumerate(blocks):
        parsed = _parse_crm_block(block)
        if not parsed:
            continue
        physician_id = parsed.get("physician_id", f"UNKNOWN_{idx}")
        name = parsed.get("name", "Unknown Physician")
        objection_tags = str(parsed.get("objection_tags", "")).strip()
        text = (
            f"CRM notes for {name} ({physician_id}). "
            f"Date: {parsed.get('date', 'N/A')}. "
            f"Rep notes: {parsed.get('rep_notes', '')} "
            f"Objection tags: {objection_tags}. "
            f"Objections: {parsed.get('objections', '')} "
            f"Interests: {parsed.get('interests', '')} "
            f"Next steps: {parsed.get('next_steps', '')}"
        )
        metadata = {
            "source": "crm_notes",
            "doc_type": "crm_summary",
            "physician_id": physician_id,
            "name": name,
            "objections": parsed.get("objections", ""),
            "objection_tags": objection_tags,
            "interests": parsed.get("interests", ""),
        }
        docs.append(Document(text=text, metadata=metadata, doc_id=f"crm-{physician_id}"))

        # Split high-signal fields into focused docs to improve retrieval precision.
        objection_text = str(parsed.get("objections", "")).strip()
        if objection_text:
            docs.append(
                Document(
                    text=f"Objections for {name} ({physician_id}): {objection_text}",
                    metadata={
                        "source": "crm_notes",
                        "doc_type": "crm_objections",
                        "physician_id": physician_id,
                        "name": name,
                        "objections": objection_text,
                        "objection_tags": objection_tags,
                    },
                    doc_id=f"crm-{physician_id}-objections",
                )
            )
            for topic, detail in _parse_objection_bullets(objection_text):
                docs.append(
                    Document(
                        text=f"Objection topic {topic} for {name} ({physician_id}): {detail}",
                        metadata={
                            "source": "crm_notes",
                            "doc_type": "crm_objection_topic",
                            "physician_id": physician_id,
                            "name": name,
                            "objections": detail,
                            "objection_topic": topic,
                            "objection_tags": objection_tags,
                        },
                        doc_id=f"crm-{physician_id}-obj-{topic}",
                    )
                )
        interests_text = str(parsed.get("interests", "")).strip()
        if interests_text:
            docs.append(
                Document(
                    text=f"Interests for {name} ({physician_id}): {interests_text}",
                    metadata={
                        "source": "crm_notes",
                        "doc_type": "crm_interests",
                        "physician_id": physician_id,
                        "name": name,
                        "interests": interests_text,
                        "objection_tags": objection_tags,
                    },
                    doc_id=f"crm-{physician_id}-interests",
                )
            )
    return docs


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _chunk_text_by_size(text: str, max_chars: int = 1000, overlap_chars: int = 120) -> List[str]:
    """Simple semantic-preserving chunking by paragraph with character budget."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        candidate = para if not current else f"{current}\n\n{para}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            tail = current[-overlap_chars:] if overlap_chars > 0 else ""
            current = f"{tail}\n\n{para}".strip() if tail else para
        else:
            chunks.append(para[:max_chars])
            current = para[max_chars - overlap_chars :] if len(para) > max_chars else ""
    if current.strip():
        chunks.append(current.strip())
    return [_normalize_text(c) for c in chunks if _normalize_text(c)]


def _load_kb_documents() -> List[Document]:
    """Load tempus_kb.md and chunk by section/subsection with size limits."""
    path = DATA_DIR / "tempus_kb.md"
    text = path.read_text(encoding="utf-8")
    docs: List[Document] = []
    current_h2: str | None = None
    current_h3: str | None = None
    buffer: List[str] = []
    counter = 0

    def flush_buffer() -> None:
        nonlocal counter, buffer
        if not current_h2 or not buffer:
            return
        raw_content = "\n".join(buffer).strip()
        if not raw_content:
            buffer = []
            return
        for idx, chunk in enumerate(_chunk_text_by_size(raw_content), start=1):
            counter += 1
            heading = current_h2 if not current_h3 else f"{current_h2} / {current_h3}"
            docs.append(
                Document(
                    text=chunk,
                    metadata={
                        "source": "knowledge_base",
                        "section": current_h2,
                        "subsection": current_h3 or "",
                        "chunk_index": idx,
                    },
                    doc_id=f"kb-{counter}-{heading.lower().replace(' ', '-').replace('/', '-')}",
                )
            )
        buffer = []

    for line in text.splitlines():
        if line.startswith("## "):
            flush_buffer()
            current_h2 = line[3:].strip()
            current_h3 = None
            continue
        if line.startswith("### "):
            flush_buffer()
            current_h3 = line[4:].strip()
            continue
        if current_h2 is not None:
            buffer.append(line)
    flush_buffer()
    return docs


def ingest(force: bool = False) -> None:
    """Run full ingestion pipeline into ChromaDB.

    If the Chroma directory already exists and force is False, ingestion is skipped.
    """
    _load_env()
    persist_dir = _get_chroma_persist_dir()
    persist_dir.mkdir(parents=True, exist_ok=True)

    if _index_exists(persist_dir) and not force:
        print(f"[ingest] Existing ChromaDB found at {persist_dir}, skipping re-index.")
        return

    print("[ingest] Building ChromaDB index...")

    # Configure embeddings
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")

    # Load documents from all sources
    market_docs = _load_market_data()
    crm_docs = _load_crm_notes()
    kb_docs = _load_kb_documents()

    all_docs: List[Document] = [*market_docs, *crm_docs, *kb_docs]
    print(
        f"[ingest] Loaded {len(market_docs)} market docs, "
        f"{len(crm_docs)} CRM docs, {len(kb_docs)} KB docs "
        f"(total={len(all_docs)})."
    )

    # Set up persistent Chroma client and vector store
    chroma_client = chromadb.PersistentClient(path=str(persist_dir))
    collection = chroma_client.get_or_create_collection(CHROMA_COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=collection)

    # No separate LlamaIndex storage persistence for now; Chroma is persistent.
    index = VectorStoreIndex.from_documents(
        all_docs,
        vector_store=vector_store,
        show_progress=True,
    )

    # Ensure any LlamaIndex side artifacts are persisted next to Chroma (optional)
    index.storage_context.persist(persist_dir=str(persist_dir / "llama"))

    print("[ingest] Ingestion complete.")
    print(f"[ingest] ChromaDB directory: {persist_dir}")
    print(f"[ingest] Collection name: {CHROMA_COLLECTION_NAME}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Tempus mock data into ChromaDB.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-indexing even if an existing ChromaDB is found.",
    )
    args = parser.parse_args()
    ingest(force=args.force)


if __name__ == "__main__":
    main()

