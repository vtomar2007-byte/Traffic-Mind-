"""Validated API schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CameraCreate(BaseModel):
    camera_key: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=2, max_length=120)
    location: str = Field(min_length=2, max_length=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    status: Literal["configured", "unavailable", "unconfigured"] = "configured"

    @model_validator(mode="after")
    def paired_coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must both be provided or both omitted.")
        return self


class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    camera_key: str
    name: str
    location: str
    latitude: float | None
    longitude: float | None
    status: str
    is_demo: bool
    created_at: datetime


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    severity: str
    title: str
    message: str
    source: str
    camera_id: int | None
    job_id: str | None
    supporting_metrics: dict[str, Any]
    acknowledged_at: datetime | None
    is_demo: bool
    created_at: datetime


class ForecastRequest(BaseModel):
    horizon_minutes: int = Field(default=60, ge=5, le=1440)
    is_demo: bool = False


class ForecastOut(BaseModel):
    status: str
    method: str
    horizon_minutes: int
    predicted_count: float | None
    target_at: datetime | None
    input_points: int
    mae: float | None
    rmse: float | None
    explanation: str
    is_demo: bool
    generated_at: datetime


class JobOut(BaseModel):
    id: str
    original_filename: str
    status: str
    progress: float
    total_frames: int | None
    processed_frames: int
    detection_count: int
    unique_track_count: int
    crossing_count: int
    class_counts: dict[str, int]
    error: str | None
    result_note: str | None
    model_name: str | None
    is_demo: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AckOut(BaseModel):
    alert: AlertOut
    acknowledged: bool
