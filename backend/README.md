# Backend , ReCall

FastAPI + SQLAlchemy + PostgreSQL backend for the Dynamic Multimedia Scene Retrieval System. See the repository root `README.md` for the project overview and the quickest path to running everything; this file covers backend-specific setup detail, structure, and the Elasticsearch installation walkthrough.

## Setup

1. Create a virtual environment and install dependencies:
   ```
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate      # macOS/Linux
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in a real `DATABASE_URL` for a PostgreSQL database you have running locally, and a real `JWT_SECRET_KEY` (`python -c "import secrets; print(secrets.token_hex(32))"`).
3. Install FFmpeg (provides both the `ffmpeg` and `ffprobe` binaries used by the media processing module) and make sure it's on your PATH , see `.env.example` for Windows install steps. Without it, every upload's background processing will fail with a clear `processing_error` message on the video, but the upload itself still succeeds.
4. Apply the migrations:
   ```
   alembic upgrade head
   ```
   This also runs `CREATE EXTENSION IF NOT EXISTS vector`, needed for `transcript_segments.embedding` , your PostgreSQL user needs permission to create extensions (true by default for the database owner).
5. Run the API:
   ```
   uvicorn app.main:app ,reload
   ```
6. Confirm it works: open `http://localhost:8000/health` (expect `{"status": "ok"}`). Interactive API docs are automatically available at `http://localhost:8000/docs`.

## Structure

```
app/
├── main.py         FastAPI app entry point, router registration, CORS
├── config.py       Environment-variable-driven settings (app/config.py)
├── database.py     SQLAlchemy engine/session setup
├── api/            Routers , thin, delegate to services
├── models/         SQLAlchemy ORM models, one per database table
├── schemas/        Pydantic request/response models
├── services/       Business logic
├── processing/     Media pipeline building blocks (FFmpeg, Whisper,
│                   embeddings, subtitle parsing, transcript segmentation)
└── utils/          Shared helpers (file validation, rate limiting)
```

## API overview

| Area | Routes | Notes |
|,-|,-|,-|
| Auth | `/api/auth/*` | register, login, current user, forgot/reset password |
| Users | `/api/users/*` | storage usage, password change, account deletion |
| Videos | `/api/videos/*` | upload, list, get, rename, delete, stream, thumbnail |
| Categories | `/api/categories/*` | personal collections |
| Search | `/api/search`, `/api/search/speech`, `/api/search/history` | the three search methods |
| Results | `/api/results/*` | scene detail, save/unsave, clip generation |
| Clips | `/api/clips/{clip_id}` | authenticated clip streaming |
| Admin | `/api/admin/*` | user management, shared dataset, data management, messaging |
| Admin Analytics | `/api/admin/analytics/*`, `/api/admin/evaluation/*` | operational + evaluation analytics, Elasticsearch health/backfill |

Full request/response shapes are in the interactive docs at `/docs` once the server is running , that is the authoritative reference; this table is only an orientation map.

## Database

All 15 tables are created and versioned through Alembic (`alembic/versions/`); there is no manually-maintained schema file to keep in sync. Run `alembic upgrade head` to bring a fresh database up to date, or `alembic history` to see every migration in order.

## Elasticsearch setup (optional, evaluation only)

Elasticsearch is not required to run the application or to search. It only powers the Analytics & Evaluation module's Elasticsearch comparison backend. This walkthrough targets Windows.

**1. Versions.** Install Elasticsearch 8.15.x (matching `elasticsearch==8.15.1` in `requirements.txt` , the `elasticsearch-py` client's major version must match the server's).

**2. Download and install (no Docker required).**
1. Download the Windows (.zip) build for 8.15.x from `https://www.elastic.co/downloads/elasticsearch`.
2. Extract it somewhere permanent, e.g. `C:\elasticsearch-8.15.3\`.
3. In PowerShell: `cd C:\elasticsearch-8.15.3\bin` then `.\elasticsearch.bat`.
4. Wait for `started` in the console output, and leave that window open.

   (Docker alternative, if available: `docker run -p 9200:9200 -e "discovery.type=single-node" -e "xpack.security.enabled=false" docker.elastic.co/elasticsearch/elasticsearch:8.15.3`.)

**3. Security.** Elasticsearch enables HTTPS + authentication by default; on first start the console prints an auto-generated `elastic` superuser password (copy it immediately). For a local setup, the simplest path is to disable security entirely: set `xpack.security.enabled: false` in `config\elasticsearch.yml` and restart. With security disabled, use `http://localhost:9200` and leave the username/password variables unset.

**4. `.env` values** (uncomment/adjust the block already in `.env.example`):
```
ELASTICSEARCH_ENABLED=True
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_INDEX_NAME=recall_evaluation_segments
ELASTICSEARCH_TIMEOUT_SECONDS=10
```

**5. Test the connection:** `curl http://localhost:9200` should return a JSON document with `"tagline" : "You Know, for Search"`.

**6. Restart the backend** so it picks up the new `.env` values.

**7. Create and verify the evaluation index** via Swagger (`/docs`), authenticated as an admin:
- `GET /api/admin/elasticsearch/health` -> expect `{"available": true}`.
- `POST /api/admin/elasticsearch/backfill` -> indexes every `READY` video's transcript segments.

**8. Run the Elasticsearch integration tests** (optional):
```
$env:RUN_ELASTICSEARCH_INTEGRATION_TESTS = "1"
python -m pytest tests/test_elasticsearch_service.py -v
```

**9. Run a real PostgreSQL-vs-Elasticsearch comparison** via Swagger, as an admin: `POST /api/admin/evaluation/run` with `{"search_backend": "postgresql"}`, then again with `{"search_backend": "elasticsearch"}`, then compare `GET /api/admin/analytics/evaluation?search_backend=...` between the two values.

**Common issues:**
- *Port 9200 already in use* , `netstat -ano | findstr :9200`, then `taskkill /PID <pid> /F`.
- *Certificate/SSL errors on `https://localhost:9200`* , disable security per step 3 and use plain `http://`.
- *401 Unauthorized* , password missing or security still enabled; reset the password and set `ELASTICSEARCH_USERNAME`/`ELASTICSEARCH_PASSWORD`.
- *Client/server version mismatch* , install an 8.15.x server, or upgrade the pinned client deliberately.
- *`{"available": false}` from the app* , confirm the `curl` test in step 5 works before suspecting the app; check `ELASTICSEARCH_ENABLED`/`ELASTICSEARCH_URL`.

**Disabling it again:** set `ELASTICSEARCH_ENABLED=False` and restart. Live user search is never affected either way , this setting only controls whether the Elasticsearch side of the evaluation toggle shows real data or an honest "not configured" message.

## Testing

See `tests/README.md`.
