## Tempus Sales Copilot

A FastAPI + React application that helps oncology sales reps prep for physician meetings by combining:

- **Mock market data** (provider attributes and priority scoring)
- **Mock CRM notes** (rep notes + objections + interests)
- **Tempus product knowledge base** (for grounded objection handling)
- **Pre‑call intel** (recent web updates with source links)

### Live demo

- **App**: https://tempus-sales-copilot.up.railway.app

### Tech Stack

- Python 3.11+
- FastAPI
- LlamaIndex
- OpenAI text-embedding-3-small
- GPT-4o (or Anthropic Claude via Anthropic SDK if `ANTHROPIC_API_KEY` is set)
- ChromaDB (local, persistent)
- Pandas, python-dotenv

---

## What the app does

- **Providers**
  - Lists providers ranked by `priority_score`
  - Visual priority indicator (green for high priority)
  - Filters by city / Tempus user status and search
- **Brief generation**
  - Generates a structured brief (meeting script, objection handler, priority rationale)
  - Grounds outputs in market data + CRM notes + KB retrieval
- **Chat coaching**
  - Lets a rep ask follow-ups using the generated brief context
- **Pre‑call intel**
  - Runs web search and synthesizes recent updates into sections (drug updates, publications, Tempus updates, competitive intel)
  - Shows **clickable source links** for each item
- **Outcome logging**
  - Logs meeting outcomes and updates priority score over time

---

## How it works (high level)

- **Indexing (ChromaDB + embeddings)**: `ingest.py` loads `data/market_data.csv`, `data/crm_notes.txt`, and `data/tempus_kb.md` into a vector store.
- **RAG brief generation**: `rag.py` retrieves relevant CRM + KB context and calls an LLM to return structured JSON.
- **Intel synthesis**: `intel.py` runs web search and asks an LLM to produce structured intel; source URLs come from the search results.
- **API**: `main.py` exposes endpoints used by the React UI.

---

## Local development

### Backend

1. Create and activate a virtual environment
  ```bash
   cd tempus-copilot-backend
   python -m venv .venv
   source .venv/bin/activate  # on Windows: .venv\\Scripts\\activate
  ```
2. Install dependencies
  ```bash
   pip install -r requirements.txt
  ```
3. Configure environment variables
  ```bash
   cp .env.example .env
  ```
   Then edit `.env` and fill in:
  - `OPENAI_API_KEY` — required if using OpenAI for embeddings/LLM
  - `ANTHROPIC_API_KEY` — optional; if set, Claude (`claude-sonnet-4-20250514`) is used as the LLM
  - `CHROMA_PERSIST_DIR` — path for persistent ChromaDB (default: `./chroma_db`)
  - `PORT` — FastAPI port (default: `8000`)
4. Run ingestion (first run only)
  ```bash
   python ingest.py
  ```
   This will:
  - Load `data/market_data.csv`, `data/crm_notes.txt`, and `data/tempus_kb.md`
  - Build a persistent ChromaDB index at `CHROMA_PERSIST_DIR`
   To force a full re-ingest (e.g., after editing data files):
5. Start the API server
  ```bash
   uvicorn main:app --reload
  ```
   The server will run on `http://localhost:${PORT}` (default `http://localhost:8000`).

---

