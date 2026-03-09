## Tempus Sales Copilot — Backend & RAG Pipeline

FastAPI backend and RAG pipeline to help oncology sales reps generate personalized briefs for physician meetings using mock market data, CRM notes, and a Tempus product knowledge base.

### Tech Stack

- Python 3.11+
- FastAPI
- LlamaIndex
- OpenAI text-embedding-3-small
- GPT-4o (or Anthropic Claude via Anthropic SDK if `ANTHROPIC_API_KEY` is set)
- ChromaDB (local, persistent)
- Pandas, python-dotenv

---

## Setup

1. **Create and activate a virtual environment (recommended)**

   ```bash
   cd tempus-copilot-backend
   python -m venv .venv
   source .venv/bin/activate  # on Windows: .venv\\Scripts\\activate
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   ```bash
   cp .env.example .env
   ```

   Then edit `.env` and fill in:

   - `OPENAI_API_KEY` — required if using OpenAI for embeddings/LLM
   - `ANTHROPIC_API_KEY` — optional; if set, Claude (`claude-sonnet-4-20250514`) is used as the LLM
   - `CHROMA_PERSIST_DIR` — path for persistent ChromaDB (default: `./chroma_db`)
   - `PORT` — FastAPI port (default: `8000`)

   **Jira integration (Action Items):**
   - `JIRA_BASE_URL` — e.g. `https://your-org.atlassian.net`
   - `JIRA_EMAIL` — your Atlassian account email
   - `JIRA_API_TOKEN` — create at [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
   - `JIRA_PROJECT_KEY` — existing project key (e.g. `SALES`). Ensure the project has the "Task" issue type enabled.

4. **Run ingestion (first run only)**

   ```bash
   python ingest.py
   ```

   This will:

   - Load `data/market_data.csv`, `data/crm_notes.txt`, and `data/tempus_kb.md`
   - Build a persistent ChromaDB index at `CHROMA_PERSIST_DIR`

   To force a full re-ingest (e.g., after editing data files):

   ```bash
   python ingest.py --force
   ```

5. **Start the API server**

   ```bash
   uvicorn main:app --reload
   ```

   The server will run on `http://localhost:${PORT}` (default `http://localhost:8000`).

---

## API Endpoints

### `GET /health`

Simple healthcheck.

**Response**

```json
{
  "status": "ok",
  "index_ready": true
}
```

---

### `POST /brief`

Generate a structured brief for a given physician using RAG over market data, CRM notes, and the Tempus knowledge base.

**Request body**

```json
{
  "physician_name": "Dr. Sarah Chen"
}
```

**Response body**

```json
{
  "physician": {
    "physician_id": "PHY001",
    "name": "Dr. Sarah Chen",
    "specialty": "Medical Oncology",
    "institution": "Northwestern Memorial Hospital",
    "city": "Chicago",
    "state": "IL",
    "estimated_annual_patients": 420,
    "current_tempus_user": false,
    "primary_cancer_focus": "NSCLC colorectal",
    "last_contact_date": "2025-11-14",
    "priority_score": 8.2
  },
  "meeting_script": "...",
  "objection_handler": "...",
  "priority_rationale": "...",
  "retrieved_kb_chunks": [
    "KB chunk text 1 ...",
    "KB chunk text 2 ..."
  ]
}
```

**Example `curl`**

```bash
curl -X POST "http://localhost:8000/brief" \
  -H "Content-Type: application/json" \
  -d '{"physician_name": "Dr. Sarah Chen"}'
```

---

### `GET /providers`

Return ranked providers by `priority_score`, optionally filtered by city.

**Query params**

- `city` (optional): filter by city (e.g. `Chicago`)
- `limit` (optional, default 10): max number of providers (1–50)

**Response body**

```json
[
  {
    "physician_id": "PHY013",
    "name": "Dr. Rachel Green",
    "institution": "Northwestern Memorial Hospital",
    "specialty": "Thoracic Oncology",
    "priority_score": 8.4,
    "primary_cancer_focus": "NSCLC immunotherapy",
    "current_tempus_user": false,
    "last_contact_date": "2025-11-12",
    "rank": 1
  }
]
```

**Example `curl`**

```bash
curl "http://localhost:8000/providers?city=Chicago&limit=10"
```

---

## Re-ingesting Data

If you modify any of the mock data files under `data/`, rerun ingestion with the `--force` flag to rebuild the index:

```bash
python ingest.py --force
```

This will recreate the ChromaDB index at `CHROMA_PERSIST_DIR`.

---

## Notes

- In a real deployment, avoid logging PII. This demo only logs high-level LLM call latency.
- CORS is configured to allow all origins so a frontend on a different domain can call the API.

