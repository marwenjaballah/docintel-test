# Changelog

## Task 1: DB sessions and auth (tickets 2 & 5)
- Killed the global DB session in app/db.py and added a get_db() dependency, so each request gets its own.
- Switched the key check to secrets.compare_digest. The old compare was open to timing attacks.
- GET /results/{rid} wasn’t behind auth. It is now.
- /extract, /match and /results/{rid} all use get_db.
- Uploads are saved under a UUID instead of the user’s filename, so no more path traversal.
- Stopped logging raw CV text. It was leaking PII.
- /match now has real MatchRequest and MatchResult types.
- Errors were returning {"error": ...} with a 200. They’re proper 404/500s now.
- Added tests for authed results, the 404 and /match validation.

## Task 2: Async extraction with Celery (tickets 1 & 15)
- Added celery==5.4.0 and redis==5.0.7 to requirements.
- New settings in app/config.py: redis_url and celery_task_always_eager.
- Result now has status (pending/completed/failed) and an error column.
- Added the ExtractJobAccepted schema for the 202 response, and status on ResultResponse.
- New app/worker.py with the Celery app and extract_document_task. Late acks and reject-on-worker-lost are on, so a dead worker doesn’t lose jobs.
- POST /extract now queues the job and returns 202 with a polling link. GET /results/{rid} shows the status.
- Added redis and worker to docker-compose, with healthchecks.
- Test for submit (202), then poll for the result.

## Task 3: Docker image (tickets 3 & 4)
- Moved from the 1GB+ python:3.11 image to a multi-stage python:3.11-slim build.
- Runs as non-root appuser (UID 1000).
- Compiles to .pyc and deletes the .py files, so the image doesn’t ship readable source.
- .dockerignore now skips tests, venvs, local DBs, docs and caches.

## Task 4: Swagger docs and batch matching (tickets 6 & 8)
- Added descriptions and examples to the schemas so Swagger UI is readable.
- New schemas: BatchMatchRequest, BatchCandidate, RankedCandidate, BatchMatchResponse.
- Set up OpenAPI tags and metadata, plus APIKeyHeader so the Authorize button works.
- Added POST /match/batch. Send it candidates and a job description, and it scores and ranks them.
- Test for ranking order and fetching results afterward.
