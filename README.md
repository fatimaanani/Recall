# ReCall

**Dynamic Multimedia Scene Retrieval System Using Text and Audio Search**

Graduation project (Computer Science). ReCall lets you upload video and audio files, automatically transcribes and indexes their content, and then lets you search across your library by typed text or by speaking a query, jumping straight to the exact matching scene instead of scrubbing through a whole file.

## Overview

Video and audio files aren't searchable by content on their own: a filename search can't find a moment because of what was said in it. ReCall solves this by transcribing every upload at ingestion time (using an uploaded subtitle file, an embedded subtitle stream, or Whisper speech recognition, in that order of preference), indexing the resulting transcript for both exact-text and semantic search, and resolving a matched result down to a precise, playable clip.

The system supports two roles, a regular user and an administrator. A regular user's uploads are private to them; an administrator's uploads form a shared library every user can search. Administrators additionally get account management, a system-wide view of uploads, and an evaluation module for measuring retrieval quality.

## Main features

- Upload video and audio, with an optional subtitle file
- Automatic transcription (Whisper) and semantic embedding generation
- Three independent search methods: Exact Text, Semantic, and Speech-to-Text
- Scene resolution and on-demand clip generation with FFmpeg
- Private user libraries and an administrator-curated shared library
- Search history, saved (bookmarked) scenes, and personal collections
- Administrator tools: user management, shared dataset curation, system-wide upload oversight, admin-to-admin messaging, and an audit log
- Analytics & Evaluation: operational metrics plus a controlled retrieval-quality evaluation comparing PostgreSQL against Elasticsearch

## Architecture and technology stack

| Layer | Technology |
|---|---|
| Frontend | React (Vite) single-page application |
| Backend | FastAPI + SQLAlchemy, layered into routers, services, and models |
| Database | PostgreSQL 16+ with the pgvector extension |
| Migrations | Alembic |
| Speech recognition | faster-whisper (a CTranslate2 reimplementation of OpenAI Whisper) |
| Semantic embeddings | sentence-transformers (`all-MiniLM-L6-v2`, 384 dimensions) |
| Media processing | FFmpeg / ffprobe (metadata, thumbnails, clip generation) |
| Evaluation-only search backend | Elasticsearch |

The backend is organized as routers (`app/api/`) that only translate requests/exceptions to HTTP, services (`app/services/`) that hold the actual business logic, and SQLAlchemy models (`app/models/`) that mirror the real database schema. PostgreSQL is the single source of truth for all operational data.

## Search methods

ReCall implements three real, independent search methods:

- **Exact Text** -- PostgreSQL full-text search (`tsvector`/`tsquery`, `simple` configuration, GIN-indexed) for literal keyword matching.
- **Semantic** -- pgvector cosine similarity over 384-dimensional sentence embeddings, for meaning-based matching that doesn't require exact wording.
- **Speech-to-Text** -- a spoken query is transcribed with Whisper, and the transcription is run through both Exact Text and Semantic retrieval, hybrid-merged into one ranked result set.

A typed-text search (`POST /api/search`) always runs exactly one of the two branches (whichever the request specifies). A spoken query (`POST /api/search/speech`) is the only case that runs both branches together, since a transcribed query has no explicit method choice behind it.

Audio fingerprinting was considered during early planning but is not implemented; it is not a search method in this system.

## Elasticsearch's role

Elasticsearch is real, working infrastructure, but it is strictly evaluation-only. It never takes part in live user search. Its only purpose is to act as a second retrieval backend that an administrator can run the same ground-truth evaluation queries against, for comparison with PostgreSQL. If Elasticsearch is disabled or unreachable, live search and every other feature continue to work normally; only the Elasticsearch side of the evaluation module becomes unavailable.

## Requirements

- Python 3.11+
- Node.js and npm
- PostgreSQL 16+ with the [pgvector](https://github.com/pgvector/pgvector) extension available
- FFmpeg (provides both the `ffmpeg` and `ffprobe` binaries)
- Elasticsearch 8.x (optional -- only needed to use the evaluation module's Elasticsearch comparison)

## Backend setup

```
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your own `DATABASE_URL` (pointing at a PostgreSQL database you have running) and a real `JWT_SECRET_KEY` (generate one with `python -c "import secrets; print(secrets.token_hex(32))"`). Every other setting in `.env.example` has a working default and is optional.

Apply the database migrations (this also runs `CREATE EXTENSION IF NOT EXISTS vector`, so your PostgreSQL role needs permission to create extensions):

```
alembic upgrade head
```

Run the API:

```
uvicorn app.main:app --reload
```

Confirm it's running at `http://localhost:8000/health` (expect `{"status": "ok"}`). Interactive API docs are automatically available at `http://localhost:8000/docs`.

## Frontend setup

```
cd frontend
npm install
cp .env.example .env
npm run dev
```

Runs at `http://localhost:5173`. `VITE_API_BASE_URL` in `.env` should point at the backend (`http://localhost:8000` by default).

## PostgreSQL and pgvector

The backend requires PostgreSQL 16 or later with the pgvector extension installed on the server (the extension itself is created automatically by the migrations, but the pgvector package must already be available to the PostgreSQL installation). See the [pgvector installation instructions](https://github.com/pgvector/pgvector#installation) for your platform.

## Elasticsearch setup (optional, evaluation only)

Elasticsearch is not required to run or search the application. It is only needed if you want to use the Analytics & Evaluation module's Elasticsearch comparison backend.

1. Install and run a local Elasticsearch 8.x server (matching the `elasticsearch` Python client version pinned in `requirements.txt`).
2. In `backend/.env`, set `ELASTICSEARCH_ENABLED=True` and `ELASTICSEARCH_URL` (and `ELASTICSEARCH_USERNAME`/`ELASTICSEARCH_PASSWORD` if you have security enabled on your Elasticsearch server).
3. Restart the backend. An administrator can then trigger a backfill and run evaluation test cases against the Elasticsearch backend from the Analytics & Evaluation page.

## Environment variables

Both `backend/.env.example` and `frontend/.env.example` list every supported environment variable with an explanation of what it does and its default value. Copy each to `.env` and fill in your own values; never commit a real `.env` file. The variables that must be set for the backend to run at all are `DATABASE_URL` and `JWT_SECRET_KEY` -- everything else already has a working default.

## Running the application

With PostgreSQL running and both the backend and frontend dev servers started as above, open `http://localhost:5173`, choose a role (User or Administrator), and register or log in.

## Project structure

```
dynamic-scene-retrieval/
├── backend/
│   ├── app/
│   │   ├── api/          FastAPI routers (one file per resource area)
│   │   ├── models/       SQLAlchemy models, one per database table
│   │   ├── schemas/      Pydantic request/response schemas
│   │   ├── services/     Business logic
│   │   ├── processing/   Media pipeline (FFmpeg, Whisper, embeddings, subtitles, segmentation)
│   │   └── utils/        Shared helpers (file validation, rate limiting, etc.)
│   ├── alembic/versions/ Database migrations
│   ├── tests/            Backend test suite (pytest)
│   └── storage/          Uploaded media, generated clips, thumbnails (not source code)
└── frontend/
    └── src/
        ├── pages/        Top-level routed pages (Home, Search, Library, Settings, admin pages, ...)
        ├── components/   Shared UI components
        ├── services/     API client wrappers, one per backend resource area
        ├── hooks/        Shared React hooks
        └── context/      React context providers (auth, etc.)
```

## Testing

Backend:

```
cd backend
pip install -r requirements.txt
pytest
```

Unit tests always run and require no external services. A smaller set of integration tests (real PostgreSQL/pgvector persistence, real Elasticsearch, real FFmpeg clip generation) are skipped automatically unless their corresponding environment variables (`TEST_DATABASE_URL`, `RUN_ELASTICSEARCH_INTEGRATION_TESTS`, `RUN_FFMPEG_INTEGRATION_TESTS`) are set -- see `backend/tests/README.md`.

Frontend:

```
cd frontend
npm run check:logic
```

Runs a small, dependency-free Node script that exercises pure client-side session logic directly with Node's built-in assertions. There is no separate frontend unit-test framework; frontend correctness is otherwise verified through the production build and manual testing against the running backend.

## Limitations and future work

- The evaluation module's ground-truth dataset is still small, so any PostgreSQL-vs-Elasticsearch comparison should be treated as preliminary, not statistically established.
- Rate limiting is an in-memory, single-process sliding window; a production, multi-worker deployment would need a shared store such as Redis.
- Password-reset email delivery is a development-mode abstraction (the reset link is logged, not emailed); a production deployment would need a real transactional email provider.
- Whisper transcription accuracy depends on audio quality and is not specifically tuned for any one language.
