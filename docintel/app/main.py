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
from app.schemas import ExtractResponse, MatchRequest, MatchResponse, ResultResponse

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


@app.post("/extract", response_model=ExtractResponse)
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
    # avoid logging raw text to prevent pii leaks
    logger.info("extracting profile from document (%d bytes)", len(content))

    try:
        profile = get_provider().extract(text)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"extraction failed: {e}",
        )

    rid = uuid.uuid4().hex
    db.add(Result(id=rid, kind="extract", payload=json.dumps(profile)))
    await db.commit()
    return {"id": rid, "profile": profile}


@app.post("/match", response_model=MatchResponse)
async def match(
    body: MatchRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(check_auth),
):
    result = get_provider().match(body.profile, body.job_description)

    rid = uuid.uuid4().hex
    db.add(Result(id=rid, kind="match", payload=json.dumps(result)))
    await db.commit()
    return {"id": rid, **result}


# added auth check and 404 status code
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
    return {"id": obj.id, "kind": obj.kind, "result": json.loads(obj.payload)}
