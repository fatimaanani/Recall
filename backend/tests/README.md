# Backend tests

Hybrid strategy:

- **Unit tests** mock the database session (and, where relevant, the
  `SentenceTransformer` model) and never touch PostgreSQL. These always
  run, with no setup.
- **Integration tests** exercise real external services: PostgreSQL +
  pgvector (persisting a vector column, and the backfill query/lock path
  against an actual session/transaction), Elasticsearch, and real FFmpeg
  clip generation. Each category is gated behind its own environment
  variable (`TEST_DATABASE_URL`, `RUN_ELASTICSEARCH_INTEGRATION_TESTS`,
  `RUN_FFMPEG_INTEGRATION_TESTS` -- see `.env.example`) and is skipped,
  not failed, when its variable is unset.

## Running

```bash
cd backend
pip install -r requirements.txt
pytest
```

Unit tests always run. Integration tests are automatically **skipped**
(not failed) when `TEST_DATABASE_URL` is unset — see the `pg_engine`
fixture in `conftest.py`.

## Running the integration tests

1. Point `TEST_DATABASE_URL` at a PostgreSQL database with the `pgvector`
   extension installable (the fixture runs `CREATE EXTENSION IF NOT EXISTS
   vector` itself — the role just needs privilege to create it). **Use a
   throwaway/dedicated test database, never the app's real one** — the
   fixture creates and drops all tables in it.
2. Set it in `backend/.env` (see `.env.example`) or as an environment
   variable, e.g.:
   ```
   TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/scene_retrieval_test
   ```
3. Run `pytest` again — the integration tests in
   `test_media_processing_embeddings.py` will now execute instead of
   skipping.

## Schema source for integration tests

The `pg_engine` fixture builds the test schema with
`Base.metadata.create_all(engine)` — derived directly from the current
SQLAlchemy models — rather than running the project's Alembic migrations
against the test database.

This is simpler and doesn't depend on every hand-written migration being
runnable end-to-end in a fresh database, but it is a known tradeoff: it
does not prove the migration chain itself produces this exact schema. If
that guarantee becomes important later, the fixture could be switched to
run `alembic upgrade head` against `TEST_DATABASE_URL` instead.

## Why the embedding model itself isn't tested end-to-end

`test_embedding_processor.py` mocks `SentenceTransformer` rather than
downloading and running the real `all-MiniLM-L6-v2` model. Even the
PostgreSQL integration tests mock `embedding_processor.generate_embeddings`
for the same reason: the model is a multi-hundred-MB download and slow to
run, and none of these tests are trying to verify the model's output
quality — only that this codebase calls it correctly, batches it
correctly, and persists/handles its result correctly.
