"""Single-worker persisted job queue for local video processing."""
from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from backend.config import get_settings
from backend.database import SessionLocal, utc_now
from backend.models import Alert, DetectionEvent, ProcessingJob, TrafficMetric
from backend.services.detection import JobCancelled, ProcessingError, process_video

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="trafficmind-video")
_cancel_events: dict[str, threading.Event] = {}
_lock = threading.Lock()


def queue_job(job_id: str) -> None:
    with _lock:
        _cancel_events[job_id] = threading.Event()
        _executor.submit(_run_job, job_id)


def cancel_job(job_id: str) -> bool:
    with _lock:
        event = _cancel_events.get(job_id)
        if event is None:
            return False
        event.set()
        return True


def _progress(job_id: str, done: int, total: int) -> None:
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if job and job.status == "running":
            job.processed_frames = done
            job.total_frames = total
            job.progress = min(0.99, done / total) if total else 0.0
            db.commit()


def _add_alert(db, key: str, severity: str, title: str, message: str, job: ProcessingJob, metrics=None) -> None:
    if db.scalar(select(Alert.id).where(Alert.alert_key == key)) is None:
        db.add(Alert(alert_key=key, severity=severity, title=title, message=message,
                     source="video-job", camera_id=job.camera_id, job_id=job.id,
                     supporting_metrics=metrics or {}, is_demo=job.is_demo))


def _run_job(job_id: str) -> None:
    cancel_event = _cancel_events.get(job_id)
    if cancel_event is None:
        return
    settings = get_settings()
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return
        job.status = "running"
        job.started_at = utc_now()
        job.error = None
        db.commit()
        source_path = Path(job.stored_path)
        output_path = settings.data_dir / "outputs" / (job.id + ".mp4")
        created_at = job.created_at
    try:
        result = process_video(source_path, output_path, created_at,
                               lambda done, total: _progress(job_id, done, total),
                               cancel_event.is_set)
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            if job is None:
                return
            job.status = "completed"
            job.finished_at = utc_now()
            job.progress = result.processed_frames / result.total_frames if result.total_frames else 1.0
            job.total_frames = result.total_frames
            job.processed_frames = result.processed_frames
            job.detection_count = result.detection_count
            job.unique_track_count = result.unique_track_count
            job.crossing_count = result.crossing_count
            job.class_counts = result.class_counts
            job.model_name = result.model_name
            job.output_path = result.output_path
            job.result_note = result.result_note
            for item in result.detections:
                db.add(DetectionEvent(job_id=job.id, track_id=item["track_id"], class_name=item["class_name"],
                                      confidence=item["confidence"], frame_index=item["frame_index"],
                                      video_seconds=item["video_seconds"], bbox_xyxy=item["bbox_xyxy"],
                                      is_demo=job.is_demo))
            for item in result.metrics:
                db.add(TrafficMetric(camera_id=job.camera_id, job_id=job.id, interval_start=item["interval_start"],
                                     interval_seconds=item["interval_seconds"], total_detections=item["total_detections"],
                                     unique_tracks=item["unique_tracks"], line_crossings=item["line_crossings"],
                                     class_counts=item["class_counts"], count_direction=item["count_direction"],
                                     is_demo=job.is_demo, source="processed-video"))
                if item["line_crossings"] >= 15:
                    minute_key = item["interval_start"].strftime("%Y%m%dT%H%M")
                    _add_alert(db, "congestion-" + job.id + "-" + minute_key, "warning",
                               "High video flow at virtual count line",
                               "Threshold reached for crossings in one video minute; this is not a road-density measurement.",
                               job, {"line_crossings": item["line_crossings"], "threshold": 15,
                                     "window_seconds": 60, "count_direction": item["count_direction"]})
            db.commit()
    except JobCancelled:
        output_path.unlink(missing_ok=True)
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            if job:
                job.status = "cancelled"
                job.error = "Cancelled by the local operator."
                job.finished_at = utc_now()
                db.commit()
    except ProcessingError as exc:
        output_path.unlink(missing_ok=True)
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            if job:
                job.status = "failed"
                job.error = str(exc)
                job.finished_at = utc_now()
                _add_alert(db, "job-failed-" + job.id, "warning", "Local video processing failed",
                           str(exc), job, {"status": "failed"})
                db.commit()
    except Exception:
        logger.exception("Video job %s failed", job_id)
        output_path.unlink(missing_ok=True)
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            if job:
                job.status = "failed"
                job.error = "Processing failed. Check the local server log for details."
                job.finished_at = utc_now()
                _add_alert(db, "job-failed-" + job.id, "warning", "Local video processing failed",
                           job.error, job, {"status": "failed"})
                db.commit()
    finally:
        with _lock:
            _cancel_events.pop(job_id, None)


def interrupted_jobs() -> int:
    """Mark jobs lost during a process restart; no false completion state."""
    with SessionLocal() as db:
        jobs = db.scalars(select(ProcessingJob).where(ProcessingJob.status.in_(["queued", "running"]))).all()
        for job in jobs:
            job.status = "failed"
            job.error = "The local server restarted while this job was pending. Submit the video again."
            job.finished_at = utc_now()
            _add_alert(db, "job-interrupted-" + job.id, "warning", "Video job interrupted by server restart", job.error, job)
        db.commit()
        return len(jobs)


def delete_job_files(job: ProcessingJob) -> None:
    settings = get_settings()
    allowed_roots = [(settings.data_dir / "uploads").resolve(), (settings.data_dir / "outputs").resolve()]
    for value in [job.stored_path, job.output_path]:
        if not value:
            continue
        path = Path(value).resolve()
        if any(root == path.parent or root in path.parents for root in allowed_roots):
            path.unlink(missing_ok=True)
