"""Persistent entities. Demo fixtures are tagged separately from processing results."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base, UTCDateTime, utc_now


class Camera(Base):
    __tablename__ = "cameras"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    location: Mapped[str] = mapped_column(String(180))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="unconfigured")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(Text)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    total_frames: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_frames: Mapped[int] = mapped_column(Integer, default=0)
    detection_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_track_count: Mapped[int] = mapped_column(Integer, default=0)
    crossing_count: Mapped[int] = mapped_column(Integer, default=0)
    class_counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, index=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    detections: Mapped[list[DetectionEvent]] = relationship(back_populates="job", cascade="all, delete-orphan")
    metrics: Mapped[list[TrafficMetric]] = relationship(back_populates="job", cascade="all, delete-orphan")


class DetectionEvent(Base):
    __tablename__ = "detection_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True)
    track_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    class_name: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    frame_index: Mapped[int] = mapped_column(Integer)
    video_seconds: Mapped[float] = mapped_column(Float)
    bbox_xyxy: Mapped[list[float]] = mapped_column(JSON)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    job: Mapped[ProcessingJob] = relationship(back_populates="detections")


class TrafficMetric(Base):
    __tablename__ = "traffic_metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    interval_start: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    total_detections: Mapped[int] = mapped_column(Integer, default=0)
    unique_tracks: Mapped[int] = mapped_column(Integer, default=0)
    line_crossings: Mapped[int] = mapped_column(Integer, default=0)
    class_counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    count_direction: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source: Mapped[str] = mapped_column(String(32), default="processed-video")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    job: Mapped[ProcessingJob | None] = relationship(back_populates="metrics")


Index("ix_metrics_mode_time", TrafficMetric.is_demo, TrafficMetric.interval_start)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="system")
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("processing_jobs.id", ondelete="SET NULL"), nullable=True)
    supporting_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, index=True)


class ForecastRecord(Base):
    __tablename__ = "forecast_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    method: Mapped[str] = mapped_column(String(64))
    horizon_minutes: Mapped[int] = mapped_column(Integer)
    predicted_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    input_points: Mapped[int] = mapped_column(Integer, default=0)
    mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    rmse: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation: Mapped[str] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, index=True)


class ApplicationSetting(Base):
    __tablename__ = "application_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
