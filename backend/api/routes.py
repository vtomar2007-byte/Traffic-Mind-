"""Local REST API for dashboard data, video jobs, and exports."""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db, utc_now
from backend.models import Alert, Camera, DetectionEvent, ProcessingJob, TrafficMetric
from backend.schemas import AlertOut, CameraCreate, CameraOut, ForecastOut, ForecastRequest, JobOut
from backend.services.analytics import active_data_mode, analytics_response, congestion_response, dashboard_overview
from backend.services.detection import model_status
from backend.services.forecasting import create_forecast, latest_forecasts
from backend.services.jobs import cancel_job, delete_job_files, queue_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogv", ".ogg"}
CHUNK_SIZE = 1024 * 1024
MAX_ACTIVE_JOBS = 3


def job_out(job: ProcessingJob) -> JobOut:
    return JobOut(id=job.id, original_filename=job.original_filename, status=job.status,
                  progress=job.progress, total_frames=job.total_frames, processed_frames=job.processed_frames,
                  detection_count=job.detection_count, unique_track_count=job.unique_track_count,
                  crossing_count=job.crossing_count, class_counts=job.class_counts or {}, error=job.error,
                  result_note=job.result_note, model_name=job.model_name, is_demo=job.is_demo,
                  created_at=job.created_at, started_at=job.started_at, finished_at=job.finished_at)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "trafficmind", "checked_at": utc_now().isoformat()}


@router.get("/ready")
def readiness(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(select(1))
        settings = get_settings()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        (settings.data_dir / "uploads").mkdir(parents=True, exist_ok=True)
        (settings.data_dir / "outputs").mkdir(parents=True, exist_ok=True)
        return {"ready": True, "components": {"database": "ready", "local_storage": "ready",
                                               "inference": "optional", "model": model_status()}}
    except (OSError, SQLAlchemyError) as exc:
        logger.exception("Readiness dependency check failed")
        raise HTTPException(status_code=503, detail={"ready": False, "error": "A local dependency is unavailable."}) from exc


@router.get("/dashboard/overview")
def overview(db: Session = Depends(get_db)) -> dict:
    return dashboard_overview(db)


@router.get("/cameras")
def list_cameras(db: Session = Depends(get_db)) -> dict:
    mode = active_data_mode(db)
    is_demo = mode == "demo"
    items = db.scalars(select(Camera).where(Camera.is_demo.is_(is_demo)).order_by(Camera.name)).all()
    return {"data_mode": mode, "items": [CameraOut.model_validate(item).model_dump(mode="json") for item in items],
            "count": len(items)}


@router.get("/cameras/{camera_id}", response_model=CameraOut)
def camera_detail(camera_id: int, db: Session = Depends(get_db)) -> Camera:
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    return camera


@router.post("/cameras", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
def create_camera(payload: CameraCreate, db: Session = Depends(get_db)) -> Camera:
    camera = Camera(**payload.model_dump(), is_demo=False)
    db.add(camera)
    try:
        db.commit()
        db.refresh(camera)
        return camera
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A camera with this key already exists.") from exc


@router.get("/analytics/traffic")
def traffic_analytics(range: Literal["24h", "7d", "30d"] = "24h", db: Session = Depends(get_db)) -> dict:
    return analytics_response(db, range)


@router.get("/congestion")
def congestion(db: Session = Depends(get_db)) -> dict:
    return congestion_response(db)


@router.post("/forecasts", response_model=ForecastOut)
def forecast(payload: ForecastRequest, db: Session = Depends(get_db)) -> dict:
    return create_forecast(db, payload.horizon_minutes)


@router.get("/forecasts")
def forecast_history(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    return {"items": latest_forecasts(db, limit)}


@router.get("/alerts")
def list_alerts(severity: Literal["critical", "warning", "info"] | None = None,
               acknowledged: bool | None = None, limit: int = Query(default=50, ge=1, le=100),
               offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)) -> dict:
    mode = active_data_mode(db)
    stmt = select(Alert).where(Alert.is_demo.is_(mode == "demo"))
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if acknowledged is not None:
        stmt = stmt.where(Alert.acknowledged_at.is_not(None) if acknowledged else Alert.acknowledged_at.is_(None))
    items = list(db.scalars(stmt.order_by(Alert.created_at.desc()).offset(offset).limit(limit)).all())
    return {"data_mode": mode, "items": [AlertOut.model_validate(item).model_dump(mode="json") for item in items],
            "limit": limit, "offset": offset}


@router.patch("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db)) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    if alert.acknowledged_at is None:
        alert.acknowledged_at = utc_now()
        db.commit()
        db.refresh(alert)
    return alert


@router.get("/metrics")
def metric_events(job_id: str | None = None, limit: int = Query(default=100, ge=1, le=500),
                 offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)) -> dict:
    stmt = select(DetectionEvent)
    if job_id:
        stmt = stmt.where(DetectionEvent.job_id == job_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.order_by(DetectionEvent.frame_index).offset(offset).limit(limit)).all()
    return {"items": [{"id": row.id, "job_id": row.job_id, "track_id": row.track_id,
                        "class_name": row.class_name, "confidence": row.confidence,
                        "frame_index": row.frame_index, "video_seconds": row.video_seconds,
                        "bbox_xyxy": row.bbox_xyxy, "is_demo": row.is_demo,
                        "created_at": row.created_at.isoformat()} for row in items],
            "limit": limit, "offset": offset, "total": total}


@router.get("/system/status")
def system_status(db: Session = Depends(get_db)) -> dict:
    jobs = db.scalars(select(ProcessingJob.status)).all()
    return {"data_mode": active_data_mode(db), "model": model_status(),
            "jobs": {state: jobs.count(state) for state in ("queued", "running", "completed", "failed", "cancelled")},
            "storage": {"local_only": True, "uploads_private": True}}


def _valid_magic(extension: str, header: bytes) -> bool:
    if extension == ".mp4":
        return len(header) >= 8 and header[4:8] == b"ftyp"
    if extension == ".webm":
        return header.startswith(b"\x1a\x45\xdf\xa3")
    if extension in {".ogv", ".ogg"}:
        return header.startswith(b"OggS")
    return False


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_video(file: UploadFile = File(...), demo_data: bool = Form(False),
                       camera_id: int | None = Form(None), db: Session = Depends(get_db)) -> JobOut:
    settings = get_settings()
    original = Path(file.filename or "video").name[:255]
    extension = Path(original).suffix.lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        await file.close()
        raise HTTPException(status_code=415, detail="Choose an MP4, WebM, or Ogg video file.")
    model = model_status()
    if not model["ready"]:
        await file.close()
        raise HTTPException(status_code=503, detail="Local video analysis is not configured. Install the optional ML dependencies and provide local YOLO weights; no model will be downloaded automatically.")
    if camera_id is not None and db.get(Camera, camera_id) is None:
        await file.close()
        raise HTTPException(status_code=404, detail="Camera not found.")
    active = db.scalar(select(ProcessingJob.id).where(ProcessingJob.status.in_(["queued", "running"])).limit(MAX_ACTIVE_JOBS))
    if active:
        count = len(db.scalars(select(ProcessingJob.id).where(ProcessingJob.status.in_(["queued", "running"]))).all())
        if count >= MAX_ACTIVE_JOBS:
            await file.close()
            raise HTTPException(status_code=429, detail="The local processing queue is full. Wait for a job to finish.")
    upload_dir = settings.data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    stored_path = upload_dir / (job_id + extension)
    byte_count = 0
    header = b""
    try:
        with stored_path.open("xb") as destination:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                byte_count += len(chunk)
                if byte_count > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Video exceeds the configured upload size limit.")
                if len(header) < 16:
                    header += chunk[:16 - len(header)]
                destination.write(chunk)
        if byte_count == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        if not _valid_magic(extension, header):
            raise HTTPException(status_code=415, detail="The file contents do not match a supported video container.")
        job = ProcessingJob(id=job_id, original_filename=original, stored_path=str(stored_path),
                            camera_id=camera_id, status="queued", progress=0, class_counts={}, is_demo=demo_data)
        db.add(job)
        db.commit()
        db.refresh(job)
        queue_job(job.id)
        return job_out(job)
    except HTTPException:
        stored_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        stored_path.unlink(missing_ok=True)
        logger.exception("Local video upload storage failed")
        raise HTTPException(status_code=507, detail="Could not store the video in local project storage.") from exc
    finally:
        await file.close()


@router.get("/jobs")
def list_jobs(limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    items = db.scalars(select(ProcessingJob).order_by(ProcessingJob.created_at.desc()).limit(limit)).all()
    return {"items": [job_out(item).model_dump(mode="json") for item in items], "limit": limit}


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobOut:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Processing job not found.")
    return job_out(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def request_cancel(job_id: str, db: Session = Depends(get_db)) -> JobOut:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Processing job not found.")
    if job.status not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Only queued or running jobs can be cancelled.")
    if not cancel_job(job_id):
        raise HTTPException(status_code=409, detail="This job is not active in the local worker.")
    return job_out(job)


@router.get("/jobs/{job_id}/preview")
def job_preview(job_id: str, db: Session = Depends(get_db)) -> FileResponse:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Processing job not found.")
    if job.status != "completed" or not job.output_path or not Path(job.output_path).is_file():
        raise HTTPException(status_code=409, detail="An annotated preview is not available for this job.")
    return FileResponse(job.output_path, media_type="video/mp4", filename="trafficmind-preview.mp4")


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db)) -> Response:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Processing job not found.")
    if job.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Cancel and wait for the job to stop before deleting it.")
    delete_job_files(job)
    db.delete(job)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/reports/traffic.csv")
def report_csv(db: Session = Depends(get_db)) -> Response:
    mode = active_data_mode(db)
    data = analytics_response(db, "24h")
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["TrafficMind local report"])
    writer.writerow(["Data mode", mode])
    writer.writerow(["Note", data["explanation"]])
    writer.writerow(["Timestamp UTC", "Line crossings", "Per-frame detections", "Unique track observations"])
    for row in data["series"]:
        writer.writerow([row["timestamp"], row["count"], row["detections"], row["unique_tracks"]])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="trafficmind-report.csv"'})
