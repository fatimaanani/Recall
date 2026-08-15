import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, admin_analytics, auth, categories, clips, health, results, search, users, videos
from app.config import get_settings
from app.database import SessionLocal
from app.services.media_processing_service import backfill_missing_embeddings_task, recover_orphaned_processing_videos

settings = get_settings()
logger = logging.getLogger("app")

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger.setLevel(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        recovered_count = recover_orphaned_processing_videos(db)
        if recovered_count:
            logger.warning(
                "Startup recovery: marked %d orphaned PROCESSING video(s) as FAILED.", recovered_count
            )
    finally:
        db.close()

    # Runs via asyncio.to_thread so startup isn't blocked; kept on app.state
    # so asyncio doesn't garbage-collect it (it only holds a weak reference
    # otherwise).
    app.state.embedding_backfill_task = asyncio.create_task(
        asyncio.to_thread(backfill_missing_embeddings_task)
    )
    yield


app = FastAPI(
    title="Dynamic Multimedia Scene Retrieval System",
    description="Backend API for scene search, upload, and clip retrieval.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(videos.router)
app.include_router(categories.router)
app.include_router(admin.router)
app.include_router(admin_analytics.router)
app.include_router(search.router)
app.include_router(clips.router)
app.include_router(results.router)
