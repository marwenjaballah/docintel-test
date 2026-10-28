"""Locust load test suite for docintel (Ticket 17).

Run locally:
    locust -f locustfile.py --host=http://localhost:8000
"""

import os
from locust import HttpUser, between, task

API_KEY = os.getenv("API_KEY", "dev-secret-key-change-me")


class DocIntelUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self):
        self.headers = {"x-api-key": API_KEY}

    @task(3)
    def check_health(self):
        self.client.get("/health")

    @task(2)
    def test_single_match(self):
        payload = {
            "profile": {"skills": ["python", "fastapi", "docker"], "years_experience": 4},
            "job_description": "We need Python and Docker with FastAPI.",
        }
        self.client.post("/match", headers=self.headers, json=payload)

    @task(1)
    def test_batch_match(self):
        payload = {
            "job_description": "Senior Python Engineer with FastAPI and Kubernetes.",
            "candidates": [
                {"candidate_id": "c1", "name": "Jane", "skills": ["python", "fastapi"], "years_experience": 5},
                {"candidate_id": "c2", "name": "Bob", "skills": ["java"], "years_experience": 2},
            ],
        }
        self.client.post("/match/batch", headers=self.headers, json=payload)

    @task(1)
    def test_extract_and_poll(self):
        files = {"file": ("resume.txt", b"Jane Doe\nPython and FastAPI developer with 5 years experience")}
        r = self.client.post("/extract", headers=self.headers, files=files)
        if r.status_code == 202:
            poll_url = r.json().get("poll_url")
            if poll_url:
                self.client.get(poll_url, headers=self.headers)
