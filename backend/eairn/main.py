"""EAIRN backend entrypoint.

    uvicorn eairn.main:app --reload

On startup the app creates its schema, installs the default rubric and loads the
seed peer cohorts, so a fresh checkout is one command away from a working API.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from eairn.api import router
from eairn.benchmarks import install_cohorts
from eairn.config import get_settings
from eairn.db import init_db, session_scope
from eairn.rubric import get_rubric, install_rubric

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with session_scope() as session:
        if get_rubric(session, settings.default_rubric_version) is None:
            install_rubric(session, settings.default_rubric_version)
        install_cohorts(session)
    yield


app = FastAPI(
    title="Enterprise AI Readiness Navigator",
    version="2.0.0",
    summary="Evidence-backed, vendor-neutral AI readiness assessment over enterprise data estates.",
    description=(
        "EAIRN connects read-only to the metadata, governance, lineage, catalog, quality and "
        "security layers of a data estate, computes a weighted readiness score across eight "
        "pillars from machine evidence, benchmarks against anonymised peers, and produces a "
        "prioritised, costed remediation roadmap. Every score is traceable to the evidence "
        "records that produced it, and every assessment run is an immutable, replayable snapshot."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health", tags=["meta"])
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "rubric_version": settings.default_rubric_version,
        "confidence_threshold": settings.confidence_threshold,
        "row_sampling_enabled": settings.allow_row_sampling,
        "advisor": "llm" if settings.anthropic_api_key else "template",
    }
