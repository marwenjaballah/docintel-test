import asyncio
import concurrent.futures
import json
import logging

from celery import Celery

from app.config import settings
from app.db import SessionLocal
from app.llm import get_provider
from app.models import Result

logger = logging.getLogger("docintel.worker")

# celery application
celery_app = Celery(
    "docintel",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# ticket 15: worker reliability settings
celery_app.conf.update(
    task_acks_late=True,  # ack only after execution finishes
    task_reject_on_worker_lost=True,  # re-queue task if worker terminates unexpectedly
    task_always_eager=settings.celery_task_always_eager,
    broker_connection_retry_on_startup=True,
)


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


async def _save_extraction_result(result_id: str, profile: dict = None, error: str = None):
    async with SessionLocal() as db:
        obj = await db.get(Result, result_id)
        if obj:
            if error:
                obj.status = "failed"
                obj.error = error
            else:
                obj.status = "completed"
                obj.payload = json.dumps(profile)
            await db.commit()


@celery_app.task(name="tasks.extract_document", bind=True, max_retries=3)
def extract_document_task(self, result_id: str, text: str):
    logger.info("worker started extraction for result_id=%s", result_id)
    try:
        profile = get_provider().extract(text)
        _run_async(_save_extraction_result(result_id, profile=profile))
        logger.info("worker completed extraction for result_id=%s", result_id)
        return {"status": "completed", "result_id": result_id}
    except Exception as exc:
        logger.error("worker extraction failed for result_id=%s: %s", result_id, exc)
        _run_async(_save_extraction_result(result_id, error=str(exc)))
        raise exc
