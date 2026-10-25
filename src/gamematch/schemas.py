from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

GameId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
UserId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UserId | None = None
    positive_game_ids: list[GameId] = Field(default_factory=list, max_length=100)
    exclude_game_ids: list[GameId] = Field(default_factory=list, max_length=100)
    n: int = Field(default=10, ge=1, le=50)
    genre: str | None = Field(default=None, max_length=80)


class InteractionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    positive_game_ids: list[GameId] = Field(min_length=1, max_length=100)


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UserId | None = None
    game_id: GameId
    value: Literal["useful", "not_relevant", "already_played"]
    model_version: str | None = Field(default=None, max_length=80)


class RecommendationItem(BaseModel):
    game_id: str
    title: str
    genres: list[str]
    tags: list[str]
    score: float
    explanation: str
    model: str


class RecommendationResponse(BaseModel):
    recommendations: list[RecommendationItem]
    model_version: str
    fallback_mode: Literal["personalized", "popularity_fallback", "no_candidates"]
