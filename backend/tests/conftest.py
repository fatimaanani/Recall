"""
conftest.py

1. Environment loading
2. Postgres/pgvector integration fixtures (skipped if unconfigured)
3. Elasticsearch client global-state reset (test isolation)
4. Rate limiter global-state reset (test isolation)
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.database import Base

# Environment loading. Reuses the same .env the app itself loads (python-
# dotenv is already a dependency) so TEST_DATABASE_URL set there is picked
# up without a separate test-only config file.
load_dotenv()

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


# Elasticsearch client global-state reset. elasticsearch_service.py
# intentionally caches its client as a module-level lazy singleton (see its
# docstring) -- _client_init_attempted flips to True the first time
# anything calls _get_client(), and every call after that raises a
# different, generic "previously failed to initialize" reason instead of
# re-checking settings.elasticsearch_enabled. Without resetting these
# between tests, whichever test happens to run first would silently decide
# the exact unavailable_reason string every other test sees -- an
# autouse fixture keeps each test's Elasticsearch state independent, the
# same way pg_session keeps each test's database state independent.
@pytest.fixture(autouse=True)
def _reset_elasticsearch_client_state():
    from app.services import elasticsearch_service

    elasticsearch_service._client = None
    elasticsearch_service._client_init_attempted = False
    yield
    elasticsearch_service._client = None
    elasticsearch_service._client_init_attempted = False


# Rate limiter global-state reset. app/utils/rate_limit.py intentionally
# keeps its request-timestamp buckets as module-level in-memory state (see
# its docstring) -- without clearing them between tests, a test earlier in
# the run that exercises a login/search/upload route enough times would
# leave a later, unrelated test's very first request already partially
# counted against the same bucket key, an order-dependent flake identical
# in spirit to the Elasticsearch fixture above.
@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    from app.utils.rate_limit import reset_rate_limits

    reset_rate_limits()
    yield
    reset_rate_limits()


# Postgres/pgvector integration fixtures. Session-scoped engine: create the
# schema once per test run, not once per test. Uses Base.metadata.create_all
# (derived from the current ORM models) rather than running the project's
# Alembic migrations against this database -- simpler, and doesn't depend
# on every hand-written migration being runnable, at the cost of not being
# a byte-for-byte proof that the migrations themselves produce this exact
# schema. See tests/README.md.
@pytest.fixture(scope="session")
def pg_engine():
    if not TEST_DATABASE_URL:
        pytest.skip(
            "TEST_DATABASE_URL is not set -- skipping PostgreSQL/pgvector integration tests. "
            "See .env.example for how to configure a test database."
        )

    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(engine)
    yield engine

    Base.metadata.drop_all(engine)
    engine.dispose()


# One test gets its own connection + transaction, rolled back afterward --
# tests never see each other's data and never need explicit cleanup, even
# across tables with foreign keys.
@pytest.fixture
def pg_session(pg_engine):
    connection = pg_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
