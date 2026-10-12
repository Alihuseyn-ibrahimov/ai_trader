"""Agent çıxışlarının sxemləri. Sxemə uymayan cavab qəbul edilmir (plan §2)."""

from typing import Literal

from pydantic import BaseModel, Field

Bias = Literal["yuxarı", "aşağı", "neytral"]
Sentiment = Literal["müsbət", "mənfi", "neytral"]
Action = Literal["AL", "ÇIX", "GÖZLƏ"]


class _Report(BaseModel):
    model_config = {"extra": "forbid"}

    def texts(self) -> list[str]:
        """Rəqəm yoxlamasından keçməli olan sərbəst mətn sahələri."""
        return []


class TechView(BaseModel):
    model_config = {"extra": "forbid"}
    pair: str
    bias: Bias
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(min_length=1, max_length=3)


class TechReport(_Report):
    views: list[TechView]

    def texts(self) -> list[str]:
        return [r for v in self.views for r in v.reasons]


class NewsView(BaseModel):
    model_config = {"extra": "forbid"}
    pair: str
    sentiment: Sentiment
    events: list[str] = Field(default_factory=list, max_length=4)


class NewsReport(_Report):
    views: list[NewsView]

    def texts(self) -> list[str]:
        return [e for v in self.views for e in v.events]


class RiskReport(_Report):
    regime: Literal["normal", "yüksək", "ekstremal"]
    max_new: int = Field(ge=0, le=2)
    reasons: list[str] = Field(min_length=1, max_length=3)

    def texts(self) -> list[str]:
        return list(self.reasons)


class Decision(BaseModel):
    model_config = {"extra": "forbid"}
    pair: str
    action: Action
    confidence: float = Field(ge=0, le=1)
    rationale: str


class SupervisorReport(_Report):
    summary: str
    decisions: list[Decision]

    def texts(self) -> list[str]:
        return [self.summary, *(d.rationale for d in self.decisions)]
