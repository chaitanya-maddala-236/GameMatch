from __future__ import annotations

import joblib
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from gamematch import api
from gamematch.db import Base, Feedback, RequestEvent, UserInteraction, get_db


def test_recommendation_api_persistence_and_metrics(toy_payload, tmp_path, monkeypatch):
    artifact = tmp_path / "model.joblib"
    joblib.dump(toy_payload, artifact)
    monkeypatch.setattr(api, "ARTIFACT_DIR", artifact)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(api, "SessionLocal", TestingSession)
    monkeypatch.setattr(api, "create_schema", lambda: Base.metadata.create_all(bind=engine))

    def override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    api.app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(api.app) as client:
            assert client.get("/health").json() == {"status": "ok"}
            assert client.get("/ready").status_code == 200

            catalog = client.get("/v1/games", params={"search": "Portal", "limit": 1}).json()
            assert catalog["total"] == 2
            assert len(catalog["items"]) == 1

            saved = client.put("/v1/users/alex-demo/interactions", json={"positive_game_ids": ["10"]})
            assert saved.status_code == 200
            stored = TestingSession().scalars(select(UserInteraction)).all()
            assert len(stored) == 1
            assert stored[0].user_hash != "alex-demo"

            recs = client.get("/v1/users/alex-demo/recommendations", params={"n": 3}).json()
            assert recs["fallback_mode"] == "personalized"
            assert all(row["game_id"] != "10" for row in recs["recommendations"])

            feedback = client.post("/v1/feedback", json={"user_id": "alex-demo", "game_id": "20", "value": "useful"})
            assert feedback.status_code == 200
            metrics = client.get("/v1/metrics/summary").json()
            assert metrics["production"]["requests"] > 0
            assert metrics["production"]["feedback_counts"]["useful"] == 1

            invalid = client.post("/v1/recommendations", json={"n": 100})
            assert invalid.status_code == 422
            events = TestingSession().scalars(select(RequestEvent)).all()
            assert all("alex-demo" not in event.route for event in events)
            feedback_rows = TestingSession().scalars(select(Feedback)).all()
            assert len(feedback_rows) == 1
    finally:
        api.app.dependency_overrides.clear()
        engine.dispose()


def test_missing_model_keeps_liveness_and_reports_not_ready(tmp_path, monkeypatch):
    artifact = tmp_path / "missing-model.joblib"
    monkeypatch.setattr(api, "ARTIFACT_DIR", artifact)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(api, "SessionLocal", TestingSession)
    monkeypatch.setattr(api, "create_schema", lambda: Base.metadata.create_all(bind=engine))

    def override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    class NoopThread:
        def __init__(self, **kwargs):
            self.target = kwargs["target"]
            self.args = kwargs["args"]

        def start(self):
            return None

    monkeypatch.setattr(api, "Thread", NoopThread)
    api.app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(api.app) as client:
            assert client.get("/health").status_code == 200
            readiness = client.get("/ready")
            assert readiness.status_code == 503
            assert readiness.json()["detail"]["model_ready"] is False
            assert readiness.json()["detail"]["bootstrap_status"] == "running"
    finally:
        api.app.dependency_overrides.clear()
        engine.dispose()
