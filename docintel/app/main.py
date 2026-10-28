import json
import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Response, Security, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import engine, get_db
from app.llm import get_provider
from app.models import Base, Result
from app.observability import ObservabilityMiddleware, setup_logging
from app.schemas import (
    BatchMatchRequest,
    BatchMatchResponse,
    ErrorResponse,
    ExtractJobAccepted,
    MatchRequest,
    MatchResponse,
    RankedCandidate,
    ResultResponse,
)
from app.worker import extract_document_task

setup_logging()
logger = logging.getLogger("docintel")

UPLOAD_DIR = "uploads"


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="docintel API",
    description="Document Intelligence Service for candidate CV extraction, scoring, and candidate ranking.",
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Health", "description": "Liveness and operational checks"},
        {"name": "Extraction", "description": "Asynchronous document profile extraction pipeline"},
        {"name": "Matching", "description": "Candidate scoring and ranking against job requirements"},
        {"name": "Results", "description": "Query historical and queued task results"},
        {"name": "Observability", "description": "Prometheus metrics and runtime telemetry"},
    ],
)

# observability and tracing middleware
app.add_middleware(ObservabilityMiddleware)

# cors configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


def check_auth(x_api_key: str = Security(api_key_header)):
    if not x_api_key or not secrets.compare_digest(
        x_api_key.encode("utf-8"), settings.api_key.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid api key",
        )


# deep health check
@app.get("/health", tags=["Health"], summary="Deep Health & Readiness Check")
async def health(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error("database health check failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    return {"status": "ok"}


# prometheus metrics endpoint
@app.get("/metrics", tags=["Observability"], summary="Prometheus Metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post(
    "/extract",
    tags=["Extraction"],
    summary="Enqueue CV Profile Extraction",
    description="Accepts a document upload, safely stores it, and enqueues an asynchronous extraction job.",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ExtractJobAccepted,
    responses={
        202: {"description": "Extraction job accepted and queued"},
        401: {"model": ErrorResponse, "description": "Missing or invalid API key"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def extract(
    file: UploadFile = File(..., description="CV document file (txt, pdf)"),
    db: AsyncSession = Depends(get_db),
    _=Depends(check_auth),
):
    content = await file.read()

    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}_{os.path.basename(file.filename or 'upload')}"
        with open(os.path.join(UPLOAD_DIR, safe_name), "wb") as f:
            f.write(content)
    except Exception as e:
        logger.warning("could not save upload: %s", e)

    text_content = content.decode("utf-8", errors="ignore")
    logger.info("queued extraction job for document (%d bytes)", len(content))

    rid = uuid.uuid4().hex
    db.add(Result(id=rid, kind="extract", status="pending", payload=None))
    await db.commit()

    extract_document_task.delay(rid, text_content)

    return {
        "id": rid,
        "status": "pending",
        "poll_url": f"/results/{rid}",
    }


@app.post(
    "/match",
    tags=["Matching"],
    summary="Score Single Candidate Profile",
    description="Scores an extracted candidate profile against a job description.",
    response_model=MatchResponse,
    responses={
        200: {"description": "Match result computed successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
)
async def match(
    body: MatchRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(check_auth),
):
    result = get_provider().match(body.profile, body.job_description)

    rid = uuid.uuid4().hex
    db.add(Result(id=rid, kind="match", status="completed", payload=json.dumps(result)))
    await db.commit()
    return {"id": rid, **result}


@app.post(
    "/match/batch",
    tags=["Matching"],
    summary="Batch Match and Rank Candidates",
    description="Evaluates multiple candidate profiles against a job description and returns a ranked shortlist.",
    response_model=BatchMatchResponse,
    responses={
        200: {"description": "Candidates evaluated and ranked"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
)
async def batch_match(
    body: BatchMatchRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(check_auth),
):
    provider = get_provider()
    scored_candidates = []

    for cand in body.candidates:
        match_out = provider.match({"skills": cand.skills}, body.job_description)
        scored_candidates.append({
            "candidate_id": cand.candidate_id,
            "name": cand.name,
            "score": match_out["score"],
            "matched_skills": match_out["matched_skills"],
            "missing_skills": match_out.get("missing_skills") or [],
            "rationale": match_out["rationale"],
        })

    scored_candidates.sort(key=lambda c: c["score"], reverse=True)

    rankings = [
        RankedCandidate(rank=idx + 1, **cand)
        for idx, cand in enumerate(scored_candidates)
    ]

    scores = [c["score"] for c in scored_candidates]
    highest = max(scores) if scores else 0
    average = round(sum(scores) / len(scores), 2) if scores else 0.0

    rid = uuid.uuid4().hex
    batch_payload = {
        "total_candidates": len(scored_candidates),
        "highest_score": highest,
        "average_score": average,
        "rankings": [r.model_dump() for r in rankings],
    }

    db.add(Result(id=rid, kind="batch_match", status="completed", payload=json.dumps(batch_payload)))
    await db.commit()

    return {
        "id": rid,
        "total_candidates": len(scored_candidates),
        "highest_score": highest,
        "average_score": average,
        "rankings": rankings,
    }


@app.get(
    "/results/{rid}",
    tags=["Results"],
    summary="Retrieve Result by ID",
    description="Retrieves the result and completion status of an extraction or match operation.",
    response_model=ResultResponse,
    responses={
        200: {"description": "Result record found"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Result not found"},
    },
)
async def get_result(
    rid: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(check_auth),
):
    obj = await db.get(Result, rid)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="result not found",
        )

    parsed_result = json.loads(obj.payload) if obj.payload else None
    return {
        "id": obj.id,
        "kind": obj.kind,
        "status": obj.status,
        "result": parsed_result,
        "error": obj.error,
    }
