import os

os.environ["DATABASE_URL"] = (
    "sqlite+aiosqlite:///./test_docintel.db"  # tests run on SQLite
)

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

settings.llm_latency = 0  # don't wait for fake model in tests


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


def test_extract_ok(client):
    r = client.post(
        "/extract",
        headers={"x-api-key": settings.api_key},
        files={"file": ("cv.txt", b"Jane Doe\nPython and FastAPI, 5 years")},
    )
    assert r.status_code == 200
    assert "python" in r.json()["profile"]["skills"]


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
    # test match endpoint with typed request schema
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
    assert res.json()["kind"] == "match"
