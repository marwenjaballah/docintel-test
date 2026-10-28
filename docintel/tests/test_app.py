import os

os.environ["DATABASE_URL"] = (
    "sqlite+aiosqlite:///./test_docintel.db"  # tests run on SQLite
)

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.worker import celery_app

# test configurations: no latency, synchronous celery execution
settings.llm_latency = 0
settings.celery_task_always_eager = True
celery_app.conf.task_always_eager = True

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    # cleanup test db after suite
    if os.path.exists("test_docintel.db"):
        try:
            os.remove("test_docintel.db")
        except OSError:
            pass


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_extract_requires_auth(client):
    r = client.post("/extract", files={"file": ("cv.txt", b"Python developer")})
    assert r.status_code == 401


def test_extract_invalid_key(client):
    r = client.post(
        "/extract",
        headers={"x-api-key": "wrong-key"},
        files={"file": ("cv.txt", b"Python developer")},
    )
    assert r.status_code == 401


def test_extract_async_202_and_poll(client):
    # submit extraction job
    r = client.post(
        "/extract",
        headers={"x-api-key": settings.api_key},
        files={"file": ("cv.txt", b"Jane Doe\nPython and FastAPI, 5 years")},
    )
    assert r.status_code == 202
    data = r.json()
    assert "id" in data
    assert data["status"] == "pending"
    assert data["poll_url"] == f"/results/{data['id']}"

    # in eager mode, the worker executes immediately; verify result
    res = client.get(
        data["poll_url"],
        headers={"x-api-key": settings.api_key},
    )
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["id"] == data["id"]
    assert res_data["status"] == "completed"
    assert "python" in res_data["result"]["skills"]


def test_results_requires_auth(client):
    r = client.get("/results/nonexistent-id")
    assert r.status_code == 401


def test_results_not_found(client):
    r = client.get(
        "/results/nonexistent-id",
        headers={"x-api-key": settings.api_key},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "result not found"


def test_match_and_fetch_result(client):
    payload = {
        "profile": {"skills": ["python", "fastapi"]},
        "job_description": "We need Python and FastAPI with Docker.",
    }
    r = client.post(
        "/match",
        headers={"x-api-key": settings.api_key},
        json=payload,
    )
    assert r.status_code == 200
    data = r.json()
    assert "id" in data
    assert data["score"] > 0
    assert "python" in data["matched_skills"]

    # fetch result by id
    res = client.get(
        f"/results/{data['id']}",
        headers={"x-api-key": settings.api_key},
    )
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["kind"] == "match"
    assert res_data["status"] == "completed"


def test_batch_match(client):
    payload = {
        "job_description": "We need Python and FastAPI with Docker.",
        "candidates": [
            {
                "candidate_id": "cand_01",
                "name": "Alice Developer",
                "skills": ["python", "fastapi", "docker"],
                "years_experience": 5,
            },
            {
                "candidate_id": "cand_02",
                "name": "Bob Junior",
                "skills": ["java"],
                "years_experience": 1,
            },
        ],
    }

    # unauthorized check
    unauth = client.post("/match/batch", json=payload)
    assert unauth.status_code == 401

    # authorized batch match
    r = client.post(
        "/match/batch",
        headers={"x-api-key": settings.api_key},
        json=payload,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total_candidates"] == 2
    assert data["highest_score"] == 100
    assert len(data["rankings"]) == 2
    # assert Alice is ranked 1st
    assert data["rankings"][0]["candidate_id"] == "cand_01"
    assert data["rankings"][0]["rank"] == 1
    assert data["rankings"][1]["candidate_id"] == "cand_02"
    assert data["rankings"][1]["rank"] == 2

    # verify persistence and retrieval
    batch_res = client.get(
        f"/results/{data['id']}",
        headers={"x-api-key": settings.api_key},
    )
    assert batch_res.status_code == 200
    assert batch_res.json()["kind"] == "batch_match"
