import json
import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

# context variable for request correlation id
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

# prometheus metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP request count",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
)


# structured json log formatter
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(""),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)


# middleware to attach request id and measure metrics
class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_ctx.set(req_id)

        start_time = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code="500",
            ).inc()
            request_id_ctx.reset(token)
            raise

        duration = time.perf_counter() - start_time
        response.headers["x-request-id"] = req_id

        # record metrics
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=str(response.status_code),
        ).inc()
        REQUEST_LATENCY.labels(endpoint=request.url.path).observe(duration)

        request_id_ctx.reset(token)
        return response
