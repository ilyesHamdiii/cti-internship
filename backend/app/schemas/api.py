from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    display_name: str
    role: str


class ReviewRequest(BaseModel):
    revision_number: int | None = None
    comment: str | None = None


class RequestChangesRequest(BaseModel):
    revision_number: int | None = None
    comment: str = Field(min_length=1)


class TelemetrySourceCreate(BaseModel):
    name: str
    category: str
    platform: str
    enabled: bool = True
    retention_days: int = Field(gt=0)
    fields: list[str]
    owner: str | None = None


class SettingUpdate(BaseModel):
    value: dict[str, Any]


class MispIngestionScheduleUpdate(BaseModel):
    enabled: bool = True
    mode: str = Field(pattern="^(disabled|interval|hourly|daily|weekly|once)$")
    run_at: datetime | None = None
    time_of_day: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    weekday: int | None = Field(default=None, ge=0, le=6)
    timezone_offset_minutes: int = 0


class ListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class DashboardSummary(BaseModel):
    pending_cti: int
    running_graphs: int
    queued_reviews: int
    coverage_percent: float
    visibility_percent: float
    average_confidence: float
    average_cost: float
    average_runtime_ms: float
    generated_at: datetime
