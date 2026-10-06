from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty


def _ensure_schema() -> None:
    """create_all 不会给已存在的表补列；这里对新增列做一次幂等 ALTER。"""
    insp = inspect(engine)
    if "prep_runs" in insp.get_table_names():
        columns = {c["name"] for c in insp.get_columns("prep_runs")}
        if "bom_signature" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE prep_runs ADD COLUMN bom_signature VARCHAR(64) DEFAULT ''"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_schema()
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title="KitPrep", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
