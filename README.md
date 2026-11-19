# LLM File Analyzer

<!-- CI badge: uncomment and update when a GitHub remote is configured -->
<!-- ![CI](https://github.com/YOUR_USER/data_chunker/actions/workflows/ci.yml/badge.svg) -->

A file ingestion and chunking pipeline that converts documents into LLM-ready formats.

## What it does

1. Accepts uploads: PDF, DOCX, PPTX, XLSX, CSV, TXT, Markdown, HTML, images
2. Detects file type
3. Converts files to plain text / structured markdown
4. Chunks content with configurable strategies
5. Validates data integrity across pipeline stages
6. Sends only relevant chunks to LLMs (Claude, OpenAI, Gemini, local)

## Project structure

```
data_chunker/
├── backend/                 # FastAPI application
│   ├── main.py
│   ├── core/config.py       # App settings
│   ├── api/routes/          # HTTP route handlers
│   ├── services/            # Business logic
│   ├── models/              # Pydantic schemas
│   ├── storage/             # File I/O helpers
│   ├── db/                  # SQLAlchemy models & sessions
│   ├── alembic/             # Database migrations
│   ├── Dockerfile
│   └── utils/               # Shared utilities
├── frontend/                # Next.js + TypeScript UI
│   ├── src/
│   │   ├── app/             # App Router pages
│   │   ├── components/      # Reusable UI components
│   │   └── lib/api.ts       # API client
│   └── Dockerfile
└── docker-compose.yml       # One-command local deployment
```

## Running with Docker (recommended)

Generate an access key in your shell before starting both services. Keep it private
and enter it in the frontend's unlock screen:

```bash
export API_ACCESS_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
docker compose up --build
```

Once running:

| Service          | URL                              |
|------------------|----------------------------------|
| Frontend         | http://localhost:3000             |
| Backend API docs | http://localhost:8000/docs        |
| Health check     | http://localhost:8000/health      |
| Qdrant           | Internal Docker network only     |

The frontend and backend bind to host loopback only. Qdrant has no published host
port. All backend routes except `/health` require `Authorization: Bearer <key>`;
without a configured key they fail closed. Browser CORS preflight is handled separately.
Interactive API docs also require that header.

For a local backend launched from `backend/`, put `API_ACCESS_KEY=<random key of
at least 32 characters>` in the ignored `backend/.env`. Never use a `NEXT_PUBLIC_*`
variable for this secret. The frontend keeps the entered key only in memory and
locks on refresh. All existing curl examples require the Authorization header.

This is a single-owner workspace: the key grants access to all documents. It does
not implement separate user accounts or document ownership. Authenticated requests
are limited to `REQUESTS_PER_MINUTE=300` per worker; HTTP bodies are capped at
`MAX_REQUEST_SIZE_MB=102` before multipart parsing, with a 100 MB file limit.
Use TLS, ingress limits, worker isolation and shared rate limiting before any
remote/multi-worker deployment. Known parser dependency updates remain pending.

To stop:

```bash
docker compose down
```

### Data persistence

All uploaded files, conversions, chunks, and the SQLite database are stored in `backend/storage/`. Qdrant vector data is stored in the named Docker volume `qdrant_storage`. Both survive container restarts.

To completely reset local data:

```bash
docker compose down -v
rm -rf backend/storage/raw backend/storage/converted backend/storage/chunks \
       backend/storage/llm_payloads backend/storage/audit backend/storage/projects \
       backend/storage/app.db backend/storage/app.db-*
```

## Local semantic search with Qdrant

Docker Compose includes a local Qdrant vector database. The backend connects to it with:

```bash
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION_NAME=llm_file_chunks
```

Run the full local stack:

```bash
docker compose up --build
```

Use semantic search from the document detail page:

1. Upload a document.
2. Convert it.
3. Generate chunks.
4. Click **Index for Semantic Search**.
5. Search with `Semantic` or `Hybrid` mode.

The current embedding implementation is deterministic and local. It is useful for demos and tests because it makes no external API calls, but it is not a production-grade semantic embedding model.

Keyword search remains the fallback. If `QDRANT_URL` is not set, or Qdrant is unavailable, keyword search still works and hybrid search returns keyword results.

## Using LM Studio for local embeddings

`deterministic_demo` remains the default embedding provider. LM Studio is optional. To test real local embeddings, start LM Studio, load an embeddings-capable model, and start the local server on port `1234`.

Chat or reasoning models can appear in `/v1/models` but still fail on `/v1/embeddings`. Use an embedding model for `LM_STUDIO_EMBEDDING_MODEL`.

Verify the LM Studio server:

```bash
curl http://localhost:1234/v1/models
```

Verify embeddings:

```bash
curl http://localhost:1234/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"<embedding-model>","input":"This is a test document."}'
```

For a local backend process:

```bash
EMBEDDING_PROVIDER=lm_studio
LM_STUDIO_BASE_URL=http://localhost:1234/v1
LM_STUDIO_EMBEDDING_MODEL=<your-loaded-model-name>
```

For the Docker backend on macOS, LM Studio is running on the host, so use:

```bash
EMBEDDING_PROVIDER=lm_studio
LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1
LM_STUDIO_EMBEDDING_MODEL=<your-loaded-model-name>
```

Example Docker run:

```bash
EMBEDDING_PROVIDER=lm_studio \
LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1 \
LM_STUDIO_EMBEDDING_MODEL=<your-loaded-model-name> \
QDRANT_COLLECTION_NAME=llm_file_chunks_lmstudio \
docker compose up --build
```

The app flow is unchanged:

1. Upload
2. Convert
3. Chunk
4. Index for Semantic Search
5. Semantic Search

LM Studio is optional and no API key is required by default. If your LM Studio server expects one, set `LM_STUDIO_API_KEY`; the app never exposes this value in API responses or the UI.

If you switch embedding providers or models, the embedding vector dimension may change. If Qdrant reports a vector size mismatch, clear/recreate the Qdrant collection or use a new `QDRANT_COLLECTION_NAME`. The app will not delete Qdrant collections automatically and will not silently mix incompatible vector dimensions. Keyword search still works without Qdrant or LM Studio.

## OCR and scanned PDF support

OCR is optional, local, and disabled by default. It is intended for scanned PDFs and image-heavy files that have little or no extractable text layer. Normal text PDFs do not need OCR.

Enable OCR:

```bash
OCR_ENABLED=true
OCR_LANGUAGE=eng
```

The backend checks local OCR commands at runtime. With the default `OCR_PROVIDER=ocrmypdf`, install OCRmyPDF and Tesseract locally if you want OCR to run:

```bash
# macOS example
brew install ocrmypdf tesseract
```

If OCR dependencies are missing, conversion does not send files anywhere and does not crash by default. The app warns and continues with the existing non-OCR conversion flow because `OCR_FAIL_OPEN=true`.

Scanned PDFs are detected heuristically during profiling:

- `has_text_layer`
- `extracted_text_char_count`
- `scanned_like`
- `requires_ocr`
- `ocr_reason`

Manual OCR test flow:

1. Start the app normally.
2. Upload a normal text PDF and confirm OCR is not required.
3. Upload a scanned or image-heavy PDF and confirm the profile says OCR is needed.
4. Convert with OCR disabled and confirm the warning appears.
5. Enable OCR if local dependencies are available.
6. Re-run conversion and confirm OCR text is used.
7. Chunk and semantic search as usual.

## Chunk quality and retrieval evaluation

After a document is chunked, the document detail page includes an **Evaluation** panel. These checks are local heuristics; they do not call an LLM judge, change embeddings, or send content to external services.

Available backend endpoints:

- `GET /api/files/{document_id}/chunk-quality`
- `POST /api/files/{document_id}/retrieval-evaluation`
- `POST /api/files/{document_id}/retrieval-evaluation-set`
- `GET /api/files/{document_id}/token-efficiency`

Chunk quality reports summarize chunk counts, token ranges, empty or malformed chunks, oversized and undersized chunks, duplicate text, section-path coverage, table chunks, OCR-derived chunks, warnings, and recommendations. The response does not include full chunk text or filesystem paths.

Retrieval evaluation runs keyword, semantic, or hybrid retrieval against a query and optional expected terms or section. It returns selected chunk IDs, section paths, previews, scores, context-token totals, expected-term hits, and an estimated retrieval score. Semantic evaluation requires an indexed document; hybrid evaluation falls back to keyword when semantic search is unavailable.

Token efficiency compares selected retrieval context tokens against converted document token estimates and original file-size estimates. A standalone token-efficiency request reports available baseline estimates; retrieval evaluation includes selected-context reduction once a query has been evaluated.

## Grounded answers with citations

The document detail page's **Ask Document** panel now uses grounded answers. The app retrieves chunks first, packages them with stable citation IDs such as `[C1]`, then asks the selected provider to answer only from those chunks.

Available backend endpoint:

- `POST /api/files/{document_id}/grounded-answer`

Grounded answer responses include:

- the answer
- citation metadata for each selected chunk
- evidence strength: `strong`, `moderate`, `weak`, or `none`
- retrieved chunk count, citation count, token count, top score, and average score
- warnings when evidence is weak or unavailable

Citations refer to local document chunks, sections, and page labels when available. They are not external sources, and the API response does not expose absolute server paths or full chunk text.

If retrieval finds no relevant chunks, the app returns:

```text
I could not find an answer in the provided document context.
```

In that case, real LLM providers are not called. If evidence is weak, the app still calls the configured provider unless `LOCAL_ONLY_MODE=true`, but the response includes a warning to verify manually.

This phase does not add an LLM judge, a new provider, or a new external service. It works with the existing mock provider and configured Claude/OpenAI/Gemini adapters. For semantic grounded answers, index the document first. Hybrid grounded answers fall back to keyword retrieval when semantic search is unavailable.

## Background jobs and progress tracking

Longer operations can run as local background jobs. Jobs are stored in the SQLite `jobs` table and exposed through polling endpoints; no Redis, Celery, WebSockets, SSE, or cloud queue is required.

Job status endpoints:

- `GET /api/jobs/{job_id}`
- `GET /api/jobs?document_id=...&status=...&limit=...`
- `POST /api/jobs/{job_id}/cancel`

Document operation job endpoints:

- `POST /api/files/{document_id}/convert/job`
- `POST /api/files/{document_id}/chunk/job`
- `POST /api/files/{document_id}/index/job`
- `POST /api/files/{document_id}/retrieval-evaluation/job`
- `POST /api/files/{document_id}/grounded-answer/job`

Existing synchronous endpoints still exist and behave as before. The document detail page now shows job buttons and progress bars for conversion, chunking, indexing, retrieval evaluation, and grounded answers. The UI polls job status every 1.5 seconds and stops polling once a job is `succeeded`, `failed`, or `canceled`.

Each job records:

- job type and document ID
- status: `queued`, `running`, `succeeded`, `failed`, or `canceled`
- progress percentage
- current step and message
- sanitized result JSON or safe error text
- timestamps

Cancel is best effort for in-process work. Running tasks check cancellation between major steps, but an operation already inside conversion, OCR, embedding, Qdrant upsert, or provider calls may finish before cancellation is observed.

On backend startup, stale queued/running jobs older than the cleanup threshold are marked interrupted. Jobs do not resume automatically after process restart.

Typical flow:

1. Upload
2. Convert as job
3. Chunk as job
4. Index as job
5. Run retrieval evaluation as job
6. Ask grounded answer as job

### Qdrant troubleshooting

**UI shows "Qdrant not configured" but Docker Compose is running:**

Check that the backend container has the correct environment variable:

```bash
docker compose exec backend env | grep QDRANT
# Should show: QDRANT_URL=http://qdrant:6333
```

**UI shows "Qdrant unavailable":**

The backend can see the URL but cannot connect. Verify Qdrant is healthy:

```bash
curl http://localhost:6333/collections
```

From inside the backend container:

```bash
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://qdrant:6333/collections').read().decode()[:300])"
```

**Qdrant is connected but semantic search doesn't work:**

You need to click **Index for Semantic Search** on the document detail page after chunking. Semantic search only works on documents that have been indexed into Qdrant.

The document detail page shows the current index status:
- **Not indexed** — click the Index button
- **Indexed (N)** — semantic search is ready

**Verify Qdrant collections from host:**

```bash
curl http://localhost:6333/collections
# Should show collection "llm_file_chunks"
```

### Troubleshooting

**Port 8000 or 3000 already in use:**
Stop the conflicting process or change ports in `docker-compose.yml`:
```yaml
ports:
  - "9000:8000"  # maps host 9000 → container 8000
```

**Rebuild images after dependency changes:**
```bash
docker compose build --no-cache
```

**Migration errors on startup:**
Check backend logs:
```bash
docker compose logs backend
```
If migrations fail, the backend will not start (by design). Fix the migration issue and rebuild.

**Frontend cannot reach backend:**
The frontend calls the backend at `http://localhost:8000` from your browser. Make sure the backend container is running and port 8000 is mapped.

## Running locally (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/health`

Interactive docs: `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open: `http://localhost:3000`

## Continuous Integration

Every push and pull request runs three CI checks via GitHub Actions:

| Job | What it checks |
|-----|----------------|
| **Backend Tests** | Installs Python 3.12 deps, runs Alembic migrations, runs pytest (391+ tests) |
| **Frontend Build** | Installs Node 20 deps, runs ESLint, runs `npm run build` (TypeScript + Next.js) |
| **Docker Compose Check** | Validates `docker-compose.yml` syntax and builds both Docker images |

To run the same checks locally:

```bash
# Backend tests
cd backend
pip install -r requirements-dev.txt
pytest --tb=short -q

# Frontend build
cd frontend
npm ci
npm run lint
npm run build

# Docker Compose
docker compose config --quiet
docker compose build
```

If CI fails, check the failing job's logs in the GitHub Actions tab. The most common causes are:
- **Backend**: a new dependency missing from `requirements.txt`, or a test relying on local state
- **Frontend**: TypeScript type errors or ESLint violations
- **Docker**: Dockerfile syntax or a dependency that fails to install in the container

## Current status

Phases 1–7 are complete. Phase 8 includes single-owner API-key authentication
and per-worker rate limiting. Production hardening is still in progress.
