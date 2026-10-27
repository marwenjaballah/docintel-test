import json
import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import engine, get_db
from app.llm import get_provider
from app.models import Base, Result
from app.schemas import ExtractJobAccepted, MatchRequest, MatchResponse, ResultResponse
from app.worker import extract_document_task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("docintel")

UPLOAD_DIR = "uploads"


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="docintel", version="0.1.0", lifespan=lifespan)

# cors configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# constant-time auth check to prevent timing attacks
def check_auth(x_api_key: str = Header(default=None)):
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid api key",
        )


@app.get("/health")
async def health():
    return {"status": "ok"}


# ticket 1: asynchronous offloading with 202 Accepted
@app.post(
    "/extract",
    response_model=ExtractJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def extract(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(check_auth),
):
    content = await file.read()

    # sanitize filename to prevent path traversal
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}_{os.path.basename(file.filename or 'upload')}"
        with open(os.path.join(UPLOAD_DIR, safe_name), "wb") as f:
            f.write(content)
    except Exception as e:
        logger.warning("could not save upload: %s", e)

    text = content.decode("utf-8", errors="ignore")
    logger.info("queued extraction job for document (%d bytes)", len(content))

    rid = uuid.uuid4().hex
    db.add(Result(id=rid, kind="extract", status="pending", payload=None))
    await db.commit()

    # dispatch task to celery queue
    extract_document_task.delay(rid, text)

    return {
        "id": rid,
        "status": "pending",
        "poll_url": f"/results/{rid}",
    }


@app.post("/match", response_model=MatchResponse)
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


# fetch result by id with status tracking
@app.get("/results/{rid}", response_model=ResultResponse)
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
