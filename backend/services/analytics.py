"""Time-series queries and transparent flow-based congestion summaries."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database import utc_now
from backend.models import Alert, Camera, ProcessingJob, TrafficMetric

RANGES = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}


def active_data_mode(db: Session) -> str:
    has_real = db.scalar(select(TrafficMetric.id).where(TrafficMetric.is_demo.is_(False)).limit(1))
    has_real_job = db.scalar(select(ProcessingJob.id).where(ProcessingJob.is_demo.is_(False), ProcessingJob.status == "completed").limit(1))
    if has_real or has_real_job:
        return "processed_video"
    return "empty"


def metrics_for_mode(db: Session, mode: str, since: datetime | None = None) -> list[TrafficMetric]:
    if mode != "processed_video":
        return []
    stmt = select(TrafficMetric).where(TrafficMetric.is_demo.is_(False))
    if since:
        stmt = stmt.where(TrafficMetric.interval_start >= since)
    return list(db.scalars(stmt.order_by(TrafficMetric.interval_start)).all())


def build_series(rows: list[TrafficMetric], mode: str, range_name: str) -> dict:
    grouped: dict[datetime, dict] = defaultdict(lambda: {"count": 0, "detections": 0, "unique_tracks": 0, "classes": defaultdict(int)})
    for row in rows:
        stamp = row.interval_start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        bucket = grouped[stamp]
        bucket["count"] += row.line_crossings
        bucket["detections"] += row.total_detections
        bucket["unique_tracks"] += row.unique_tracks
        for name, count in (row.class_counts or {}).items():
            bucket["classes"][name] += int(count)
    series = [{"timestamp": stamp.isoformat(), "count": vals["count"],
               "detections": vals["detections"], "unique_tracks": vals["unique_tracks"],
               "classes": dict(vals["classes"])} for stamp, vals in sorted(grouped.items())]
    total = sum(point["count"] for point in series)
    return {"data_mode": mode, "range": range_name, "unit": "line_crossings_per_hour",
            "series": series, "total_line_crossings": total, "observed_intervals": len(series),
            "explanation": ("Seeded illustrative demonstration values." if mode == "demo" else
                            "Computed from persisted processed-video line crossings; not a city-wide count." if mode == "processed_video" else
                            "No traffic metric observations are available yet.")}


def congestion_level(flow_per_hour: float) -> str:
    """A configurable student-project flow proxy, not physical density or speed."""
    if flow_per_hour >= 120:
        return "high"
    if flow_per_hour >= 65:
        return "moderate"
    return "low"


def dashboard_overview(db: Session) -> dict:
    mode = active_data_mode(db)
    since = utc_now() - timedelta(hours=24)
    rows = metrics_for_mode(db, mode, since) if mode != "empty" else []
    total_flow = sum(row.line_crossings for row in rows)
    observed_camera_hours = {(row.camera_id, row.interval_start.replace(minute=0, second=0, microsecond=0)) for row in rows}
    hours = max(1, len(observed_camera_hours))
    average_flow = total_flow / hours if rows else 0
    alerts = list(db.scalars(select(Alert).where(Alert.is_demo.is_(False))).all())
    open_alerts = sum(alert.acknowledged_at is None for alert in alerts)
    class_totals: dict[str, int] = defaultdict(int)
    recent_jobs = list(db.scalars(select(ProcessingJob).where(
        ProcessingJob.is_demo.is_(False), ProcessingJob.status == "completed",
        ProcessingJob.created_at >= since).order_by(ProcessingJob.created_at)).all())
    for job in recent_jobs:
        for name, count in (job.class_counts or {}).items():
            class_totals[name] += int(count)
    return {"data_mode": mode, "vehicles_counted": sum(job.unique_track_count for job in recent_jobs) if recent_jobs else None,
            "average_speed_kmh": None, "speed_note": "Not estimated: no calibrated speed measurements are stored.",
            "congestion_level": congestion_level(average_flow) if rows else "unknown",
            "congestion_basis": "line crossings per observed hour; configurable flow proxy only",
            "active_alerts": open_alerts, "total_alerts": len(alerts), "vehicle_classes": dict(class_totals),
            "camera_count": db.scalar(select(func.count(Camera.id)).where(Camera.is_demo.is_(False))) if mode != "empty" else 0,
            "generated_at": utc_now().isoformat(),
            "data_note": ("Vehicles are unique tracked objects from locally analyzed videos; flow summaries use virtual-line crossings and are not city-wide counts." if mode == "processed_video" else
                          "No video has been analyzed yet. Upload a clip and configure local YOLO weights to populate traffic observations.")}


def analytics_response(db: Session, range_name: str) -> dict:
    mode = active_data_mode(db)
    since = utc_now() - RANGES[range_name]
    rows = metrics_for_mode(db, mode, since) if mode != "empty" else []
    return build_series(rows, mode, range_name)


def congestion_response(db: Session) -> dict:
    mode = active_data_mode(db)
    rows = metrics_for_mode(db, mode, utc_now() - timedelta(hours=24)) if mode != "empty" else []
    per_camera: dict[int | None, dict] = defaultdict(lambda: {"total": 0, "hours": set()})
    for row in rows:
        per_camera[row.camera_id]["total"] += row.line_crossings
        per_camera[row.camera_id]["hours"].add(row.interval_start.replace(minute=0, second=0, microsecond=0))
    cameras = {camera.id: camera for camera in db.scalars(select(Camera).where(Camera.is_demo.is_(mode == "demo"))).all()} if mode != "empty" else {}
    result = []
    for camera_id, stats in per_camera.items():
        camera = cameras.get(camera_id)
        observed_hours = len(stats["hours"])
        hourly_flow = stats["total"] / max(1, observed_hours)
        result.append({"camera_id": camera_id, "camera_name": camera.name if camera else "Uploaded video",
                       "location": camera.location if camera else "Video-derived observation",
                       "flow_crossings_24h": stats["total"], "observed_hours": observed_hours,
                       "flow_crossings_per_observed_hour": round(hourly_flow, 2),
                       "level": congestion_level(hourly_flow), "data_mode": mode})
    return {"data_mode": mode, "basis": "per-observed-camera-hour flow threshold proxy; no physical speed or road density estimate",
            "zones": result}
