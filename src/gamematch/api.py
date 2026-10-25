from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from threading import Thread
from typing import Any

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from gamematch import __version__
from gamematch.db import (
    Feedback,
    RequestEvent,
    SessionLocal,
    UserInteraction,
    create_schema,
    get_db,
)
from gamematch.recommendation import GameRecommender
from gamematch.schemas import (
    FeedbackRequest,
    InteractionUpdate,
    RecommendationItem,
    RecommendationRequest,
    RecommendationResponse,
)
from gamematch.settings import ARTIFACT_DIR, LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL, format="%(message)s")
logger = logging.getLogger("gamematch")
HASH_SECRET = os.getenv("PLAYER_ID_HASH_SECRET", "local-development-only-change-me").encode("utf-8")
request_history: dict[str, deque[float]] = defaultdict(deque)
rate_lock = asyncio.Lock()


def user_hash(user_id: str) -> str:
    return hmac.new(HASH_SECRET, user_id.encode("utf-8"), hashlib.sha256).hexdigest()


def _recommender(request: Request) -> GameRecommender:
    engine = getattr(request.app.state, "recommender", None)
    if engine is None:
        status = getattr(request.app.state, "bootstrap_status", "unknown")
        detail = "Model is not ready; retry after GET /ready returns 200."
        if status == "failed":
            detail = "Model bootstrap failed; inspect API logs and restart after fixing the cause."
        raise HTTPException(status_code=503, detail=detail)
    return engine


def _bootstrap_model(app: FastAPI) -> None:
    """Build the first local artifact outside request handlers, then load it."""
    try:
        from gamematch.bootstrap import main as bootstrap

        bootstrap()
        app.state.recommender = GameRecommender.load(str(ARTIFACT_DIR))
        app.state.bootstrap_status = "ready"
        logger.info(json.dumps({"event": "model_loaded", "model_version": app.state.recommender.info.get("model_version")}))
    except Exception:
        app.state.bootstrap_status = "failed"
        logger.exception(json.dumps({"event": "model_bootstrap_failed"}))


def _format_recommendations(rows: list[Any]) -> list[RecommendationItem]:
    return [
        RecommendationItem(
            game_id=str(row.game["id"]),
            title=str(row.game["title"]),
            genres=row.game.get("genres", []),
            tags=row.game.get("tags", []),
            score=round(float(row.score), 6),
            explanation=row.explanation,
            model=row.model,
        )
        for row in rows
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_schema()
    app.state.recommender = None
    app.state.bootstrap_status = "starting"
    try:
        app.state.recommender = GameRecommender.load(str(ARTIFACT_DIR))
        app.state.bootstrap_status = "ready"
        logger.info(json.dumps({"event": "model_loaded", "model_version": app.state.recommender.info.get("model_version")}))
    except FileNotFoundError:
        app.state.bootstrap_status = "running"
        logger.warning(json.dumps({"event": "model_missing_bootstrap_started", "path": str(ARTIFACT_DIR)}))
        Thread(target=_bootstrap_model, args=(app,), name="gamematch-model-bootstrap", daemon=True).start()
    except Exception:
        app.state.bootstrap_status = "failed"
        logger.exception(json.dumps({"event": "model_load_failed", "path": str(ARTIFACT_DIR)}))
    yield


app = FastAPI(
    title="GameMatch API",
    version=__version__,
    description="Explainable Steam game recommendations with held-out offline evaluation and operational metrics.",
    lifespan=lifespan,
)
cors_origins = [value.strip() for value in os.getenv("GAMEMATCH_CORS_ORIGINS", "*").split(",") if value.strip()]
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["GET", "POST", "PUT"], allow_headers=["*"])


@app.middleware("http")
async def request_observability(request: Request, call_next):
    route = request.url.path
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > 1_000_000:
        return JSONResponse(status_code=413, content={"detail": "Request body exceeds 1 MB."})
    if route.startswith("/v1/") and route != "/v1/metrics/summary":
        peer = request.client.host if request.client else "unknown"
        now = time.monotonic()
        async with rate_lock:
            history = request_history[peer]
            while history and now - history[0] > 60:
                history.popleft()
            if len(history) >= 120:
                return JSONResponse(status_code=429, content={"detail": "Per-client request limit reached; retry shortly."})
            history.append(now)
            if len(request_history) > 10_000:
                request_history.clear()
    request_id = str(uuid.uuid4())
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        route_template = getattr(request.scope.get("route"), "path", "/unmatched")
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "route": route_template,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 3),
                }
            )
        )
        try:
            with SessionLocal() as db:
                db.add(RequestEvent(route=route_template, status_code=status_code, duration_ms=duration_ms))
                db.commit()
        except Exception:
            logger.exception(json.dumps({"event": "request_metric_write_failed", "request_id": request_id}))


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["operations"])
def ready(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    model_ready = getattr(request.app.state, "recommender", None) is not None
    try:
        db.execute(select(1))
        database_ready = True
    except SQLAlchemyError:
        database_ready = False
    if not model_ready or not database_ready:
        raise HTTPException(
            status_code=503,
            detail={
                "model_ready": model_ready,
                "database_ready": database_ready,
                "bootstrap_status": getattr(request.app.state, "bootstrap_status", "unknown"),
            },
        )
    return {"status": "ready", "model_ready": True, "database_ready": True}


@app.get("/v1/model/info", tags=["model"])
def model_info(recommender: GameRecommender = Depends(_recommender)) -> dict[str, Any]:
    return recommender.model_info()


@app.get("/v1/games", tags=["catalog"])
def games(
    recommender: GameRecommender = Depends(_recommender),
    search: str | None = Query(default=None, max_length=100),
    genre: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
) -> dict[str, Any]:
    rows = recommender.catalog
    if search:
        term = search.casefold()
        rows = [row for row in rows if term in str(row["title"]).casefold()]
    if genre:
        term = genre.casefold()
        rows = [row for row in rows if term in {value.casefold() for value in row.get("genres", [])}]
    rows = sorted(rows, key=lambda row: (-int(row.get("interaction_count", 0)), str(row["title"]).casefold()))
    return {"items": rows[offset : offset + limit], "total": len(rows), "limit": limit, "offset": offset}


@app.get("/v1/games/{game_id}", tags=["catalog"])
def game(game_id: str, recommender: GameRecommender = Depends(_recommender)) -> dict[str, Any]:
    row = recommender.game(game_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Game not found.")
    return row


@app.get("/v1/games/{game_id}/similar", tags=["recommendations"])
def similar_games(
    game_id: str,
    recommender: GameRecommender = Depends(_recommender),
    model: str = Query(default="content", pattern="^(content|collaborative)$"),
    n: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    if recommender.game(game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found.")
    rows = recommender.similar(game_id, n=n, model=model)
    return {"game_id": game_id, "model": model, "recommendations": _format_recommendations(rows)}


def _profile_history(db: Session, user_id: str | None) -> list[str]:
    if not user_id:
        return []
    rows = db.scalars(select(UserInteraction.game_id).where(UserInteraction.user_hash == user_hash(user_id))).all()
    return list(rows)


def _recommend(
    recommender: GameRecommender,
    request: RecommendationRequest,
    db: Session,
) -> RecommendationResponse:
    history = list(dict.fromkeys(_profile_history(db, request.user_id) + request.positive_game_ids))
    rows, mode = recommender.recommend(
        history,
        n=request.n,
        exclude_game_ids=request.exclude_game_ids,
        genre=request.genre,
    )
    return RecommendationResponse(
        recommendations=_format_recommendations(rows),
        model_version=recommender.model_info()["model_version"],
        fallback_mode=mode,
    )


@app.get("/v1/users/{user_id}/recommendations", tags=["recommendations"], response_model=RecommendationResponse)
def user_recommendations(
    user_id: str,
    recommender: GameRecommender = Depends(_recommender),
    db: Session = Depends(get_db),
    n: int = Query(default=10, ge=1, le=50),
    genre: str | None = Query(default=None, max_length=80),
    exclude_game_ids: list[str] = Query(default=[]),
) -> RecommendationResponse:
    if len(user_id) > 128 or len(exclude_game_ids) > 100:
        raise HTTPException(status_code=422, detail="User ID or exclusion list exceeds its limit.")
    request = RecommendationRequest(user_id=user_id, n=n, genre=genre, exclude_game_ids=exclude_game_ids)
    return _recommend(recommender, request, db)


@app.post("/v1/recommendations", response_model=RecommendationResponse, tags=["recommendations"])
def recommendations(
    request: RecommendationRequest,
    recommender: GameRecommender = Depends(_recommender),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    return _recommend(recommender, request, db)


@app.put("/v1/users/{user_id}/interactions", tags=["feedback"])
def update_interactions(
    user_id: str,
    body: InteractionUpdate,
    recommender: GameRecommender = Depends(_recommender),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if len(user_id) > 128:
        raise HTTPException(status_code=422, detail="User ID is too long.")
    unknown = [game_id for game_id in body.positive_game_ids if recommender.game(game_id) is None]
    if unknown:
        raise HTTPException(status_code=422, detail={"unknown_game_ids": unknown[:10]})
    key = user_hash(user_id)
    for game_id in set(body.positive_game_ids):
        exists = db.scalar(
            select(UserInteraction.id).where(UserInteraction.user_hash == key, UserInteraction.game_id == game_id)
        )
        if exists is None:
            db.add(UserInteraction(user_hash=key, game_id=game_id))
    db.commit()
    return {"stored_interactions": len(set(body.positive_game_ids)), "identity_storage": "HMAC-SHA256 only"}


@app.post("/v1/feedback", tags=["feedback"])
def feedback(
    body: FeedbackRequest,
    recommender: GameRecommender = Depends(_recommender),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if recommender.game(body.game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found.")
    db.add(
        Feedback(
            user_hash=user_hash(body.user_id) if body.user_id else None,
            game_id=body.game_id,
            value=body.value,
            model_version=body.model_version,
        )
    )
    db.commit()
    return {"status": "recorded", "meaning": "feedback is stored for later analysis; it does not retrain the model"}


@app.get("/v1/metrics/summary", tags=["monitoring"])
def metrics_summary(db: Session = Depends(get_db), recommender: GameRecommender = Depends(_recommender)) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    rows = db.scalars(select(RequestEvent).where(RequestEvent.created_at >= cutoff, RequestEvent.route.like("/v1/%"))).all()
    latencies = np.asarray([row.duration_ms for row in rows], dtype=np.float64)
    feedback_counts = dict(
        db.execute(select(Feedback.value, func.count(Feedback.id)).where(Feedback.created_at >= cutoff).group_by(Feedback.value)).all()
    )
    count = len(rows)
    errors = sum(row.status_code >= 500 for row in rows)
    return {
        "window_hours": 24,
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "production": {
            "requests": count,
            "server_errors": errors,
            "server_error_rate": errors / count if count else None,
            "latency_ms_p50": float(np.percentile(latencies, 50)) if count else None,
            "latency_ms_p95": float(np.percentile(latencies, 95)) if count else None,
            "feedback_counts": feedback_counts,
            "feedback_is_preference_signal_not_satisfaction_proof": True,
        },
        "offline_evaluation": recommender.metrics.get("test", {}),
    }
