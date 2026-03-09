# Deploying to Railway

This app deploys as a **single service**: FastAPI backend + built React frontend.

## Quick start

1. **Connect your repo** to [Railway](https://railway.app) (New Project → Deploy from GitHub).

2. **Add environment variables** in Railway dashboard:
   - `OPENAI_API_KEY` (required for embeddings + LLM)
   - `ANTHROPIC_API_KEY` (optional; falls back to OpenAI if set)
   - `PORT` is set automatically by Railway

3. **Deploy** – Railway will:
   - Install Python deps + Node deps
   - Build the React frontend (`VITE_API_URL` left empty for same-origin)
   - Run `python ingest.py --force` to build the ChromaDB index
   - Start `uvicorn main:app`

4. **Add a volume** (recommended) for `chroma_db` so the index persists across deploys:
   - In your service → Variables → Add a Volume
   - Mount path: `chroma_db`
   - This keeps the vector index between restarts

## Build vs runtime

- **Build time**: Needs `OPENAI_API_KEY` for `ingest.py` (embeddings). Add it in Railway before the first deploy.
- **Runtime**: Same keys used for brief generation, chat, and intel.

## ChromaDB persistence

Without a volume, the index is rebuilt on every deploy (~30–60s on first request). With a volume at `chroma_db`, the index persists and startup is fast.
