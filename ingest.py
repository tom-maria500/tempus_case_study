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
from pathlib import Path
from typing import Dict, List

import chromadb
import pandas as pd
from dotenv import load_dotenv
from llama_index.core import Document, Settings, VectorStoreIndex
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

    docs: List[Document] = []
    for _, row in df.iterrows():
        physician_id = str(row["physician_id"])
        text = (
            f"Physician market data for {row['name']} ({row['physician_id']}): "
            f"specialty={row['specialty']}, institution={row['institution']}, "
            f"city={row['city']}, state={row['state']}, "
            f"estimated_annual_patients={row['estimated_annual_patients']}, "
            f"primary_cancer_focus={row['primary_cancer_focus']}, "
            f"current_tempus_user={row['current_tempus_user']}, "
            f"last_contact_date={row['last_contact_date']}, "
            f"priority_score={row['priority_score']}."
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
            "priority_score": float(row["priority_score"]),
        }
        docs.append(Document(text=text, metadata=metadata, doc_id=f"market-{physician_id}"))

    return docs


def _parse_crm_block(block: str) -> Dict:
    """Parse a single CRM notes block into structured fields."""
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    data: Dict[str, str] = {}
    for line in lines:
        if line.startswith("PHYSICIAN:"):
            # PHYSICIAN: Dr. Sarah Chen | PHY001
            rest = line.split("PHYSICIAN:", 1)[1].strip()
            if "|" in rest:
                name_part, id_part = [p.strip() for p in rest.split("|", 1)]
                data["name"] = name_part
                data["physician_id"] = id_part
            else:
                data["name"] = rest
        elif line.startswith("DATE:"):
            data["date"] = line.split("DATE:", 1)[1].strip()
        elif line.startswith("REP_NOTES:"):
            data["rep_notes"] = line.split("REP_NOTES:", 1)[1].strip()
        elif line.startswith("OBJECTIONS:"):
            data["objections"] = line.split("OBJECTIONS:", 1)[1].strip()
        elif line.startswith("INTERESTS:"):
            data["interests"] = line.split("INTERESTS:", 1)[1].strip()
        elif line.startswith("NEXT_STEPS:"):
            data["next_steps"] = line.split("NEXT_STEPS:", 1)[1].strip()
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
        text = (
            f"CRM notes for {name} ({physician_id}). "
            f"Date: {parsed.get('date', 'N/A')}. "
            f"Rep notes: {parsed.get('rep_notes', '')} "
            f"Objections: {parsed.get('objections', '')} "
            f"Interests: {parsed.get('interests', '')} "
            f"Next steps: {parsed.get('next_steps', '')}"
        )
        metadata = {
            "source": "crm_notes",
            "physician_id": physician_id,
            "name": name,
            "objections": parsed.get("objections", ""),
            "interests": parsed.get("interests", ""),
        }
        docs.append(Document(text=text, metadata=metadata, doc_id=f"crm-{physician_id}"))
    return docs


def _load_kb_documents() -> List[Document]:
    """Load tempus_kb.md and chunk by top-level ## section."""
    path = DATA_DIR / "tempus_kb.md"
    text = path.read_text(encoding="utf-8")

    sections: List[Document] = []
    current_heading: str | None = None
    current_lines: List[str] = []

    def flush_section() -> None:
        if current_heading and current_lines:
            content = "\n".join(current_lines).strip()
            if not content:
                return
            sections.append(
                Document(
                    text=content,
                    metadata={
                        "source": "knowledge_base",
                        "section": current_heading,
                    },
                    doc_id=f"kb-{current_heading.lower().replace(' ', '-')}",
                )
            )

    for line in text.splitlines():
        if line.startswith("## "):
            # New section
            flush_section()
            current_heading = line[3:].strip()
            current_lines = []
        else:
            if current_heading is not None:
                current_lines.append(line)

    flush_section()
    return sections


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

