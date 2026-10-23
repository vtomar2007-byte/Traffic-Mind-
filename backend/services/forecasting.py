"""Persist a simple moving-average forecast only when history is sufficient."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta, timezone
from math import sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import utc_now
from backend.models import ForecastRecord, TrafficMetric
from backend.services.analytics import active_data_mode, metrics_for_mode

MIN_REAL_HOURLY_POINTS = 24


def create_forecast(db: Session, horizon_minutes: int) -> dict:
    mode = active_data_mode(db)
    rows = metrics_for_mode(db, mode, utc_now() - timedelta(days=30)) if mode != "empty" else []
    buckets: dict = defaultdict(int)
    days = set()
    for row in rows:
        hour = row.interval_start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        buckets[hour] += row.line_crossings
        days.add(hour.date())
    points = sorted(buckets.items())
    sufficient = (len(points) >= 3) if mode == "demo" else (len(points) >= MIN_REAL_HOURLY_POINTS and len(days) >= 3)
    predicted = sum(value for _, value in points[-3:]) / min(3, len(points)) if sufficient else None
    target = utc_now() + timedelta(minutes=horizon_minutes) if sufficient else None
    if mode == "demo":
        explanation = ("Moving average of the final three seeded demo hourly buckets. This is a reproducible demonstration only."
                       if sufficient else "Not enough seeded demo intervals to calculate a forecast.")
    elif mode == "processed_video":
        explanation = ("Moving-average baseline from persisted video-derived hourly crossings. One video cannot establish city-wide or future-road traffic."
                       if sufficient else f"Insufficient history: need at least {MIN_REAL_HOURLY_POINTS} hourly buckets spanning three dates; found {len(points)} buckets across {len(days)} dates.")
    else:
        explanation = "No observations are available. Process video with a configured model before requesting a data-based forecast."
    record = ForecastRecord(status="ready" if sufficient else "insufficient_data",
                            method="three-hour moving average" if sufficient else "not calculated",
                            horizon_minutes=horizon_minutes, predicted_count=predicted, target_at=target,
                            input_points=len(points), explanation=explanation, is_demo=(mode == "demo"))
    db.add(record)
    db.commit()
    db.refresh(record)
    return forecast_dict(record)


def forecast_dict(record: ForecastRecord) -> dict:
    return {"status": record.status, "method": record.method, "horizon_minutes": record.horizon_minutes,
            "predicted_count": record.predicted_count, "target_at": record.target_at,
            "input_points": record.input_points, "mae": record.mae, "rmse": record.rmse,
            "explanation": record.explanation, "is_demo": record.is_demo,
            "generated_at": record.created_at}


def latest_forecasts(db: Session, limit: int = 20) -> list[dict]:
    rows = db.scalars(select(ForecastRecord).order_by(ForecastRecord.created_at.desc()).limit(limit)).all()
    return [forecast_dict(record) for record in rows]
