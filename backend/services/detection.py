"""Optional local YOLO + ByteTrack pipeline. No model downloads are performed."""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Callable

from backend.config import get_settings
from backend.database import utc_now

CLASS_IDS = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
_MODEL = None
_MODEL_PATH: Path | None = None
_MODEL_LOCK = threading.Lock()


class ProcessingError(RuntimeError):
    pass


class JobCancelled(RuntimeError):
    pass


@dataclass
class ProcessResult:
    detections: list[dict]
    metrics: list[dict]
    total_frames: int
    processed_frames: int
    detection_count: int
    unique_track_count: int
    crossing_count: int
    class_counts: dict[str, int]
    model_name: str
    output_path: str
    result_note: str


def model_status() -> dict:
    settings = get_settings()
    weight_exists = bool(settings.model_path and settings.model_path.is_file())
    try:
        import cv2  # noqa: F401
        opencv_available = True
    except ImportError:
        opencv_available = False
    try:
        import ultralytics  # noqa: F401
        ultralytics_available = True
    except ImportError:
        ultralytics_available = False
    return {"weights_configured": bool(settings.model_path), "weights_found": weight_exists,
            "opencv_available": opencv_available, "ultralytics_available": ultralytics_available,
            "ready": weight_exists and opencv_available and ultralytics_available,
            "model_path_configured": bool(settings.model_path),
            "downloads_automatic": False}


def _load_model(path: Path):
    global _MODEL, _MODEL_PATH
    if not path.is_file():
        raise ProcessingError("Configured YOLO weights were not found. Set TRAFFICMIND_MODEL_PATH to a local .pt file; no weights were downloaded.")
    with _MODEL_LOCK:
        if _MODEL is None or _MODEL_PATH != path:
            try:
                from ultralytics import YOLO
            except ImportError as exc:
                raise ProcessingError("Ultralytics is not installed. Follow the optional local ML setup in README.md.") from exc
            _MODEL = YOLO(str(path))
            _MODEL_PATH = path
        return _MODEL


def process_video(video_path: Path, output_path: Path, job_created_at,
                  progress: Callable[[int, int], None], cancelled: Callable[[], bool]) -> ProcessResult:
    settings = get_settings()
    if settings.model_path is None:
        raise ProcessingError("YOLO weights are not configured. Set TRAFFICMIND_MODEL_PATH to local weights; no download was attempted.")
    model = _load_model(settings.model_path)
    try:
        import cv2
    except ImportError as exc:
        raise ProcessingError("OpenCV is not installed. Install the optional ML dependencies described in README.md.") from exc
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        capture.release()
        raise ProcessingError("The video decoder could not open this file. Try an MP4 with H.264 video or a supported WebM file.")
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 25.0
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if width <= 0 or height <= 0:
        capture.release()
        raise ProcessingError("Video dimensions are invalid or unsupported.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        capture.release()
        raise ProcessingError("Could not create the local annotated preview video.")
    detections: list[dict] = []
    counts_by_minute: dict[int, dict] = defaultdict(lambda: {"line_crossings": 0, "total_detections": 0,
                                                              "tracks": set(), "class_counts": defaultdict(int)})
    previous_x: dict[tuple[int, str], float] = {}
    seen_tracks: set[tuple[int, str]] = set()
    counted_tracks: set[tuple[int, str]] = set()
    class_counts: dict[str, int] = defaultdict(int)
    processed = detection_count = crossing_count = 0
    line_x = width * settings.count_line_ratio
    max_frames = settings.max_video_frames
    try:
        while processed < max_frames:
            if cancelled():
                raise JobCancelled("Processing was cancelled by the user.")
            ok, frame = capture.read()
            if not ok:
                break
            frame_index = processed
            overlay: list[tuple[list[float], str, float, int | None]] = []
            if frame_index % settings.process_every_n_frames == 0:
                with _MODEL_LOCK:
                    result = model.track(frame, persist=True, tracker="bytetrack.yaml", conf=settings.confidence,
                                         classes=list(CLASS_IDS), verbose=False)[0]
                boxes = getattr(result, "boxes", None)
                if boxes is not None and len(boxes):
                    xyxy = boxes.xyxy.cpu().tolist()
                    class_ids = boxes.cls.cpu().tolist()
                    confidences = boxes.conf.cpu().tolist()
                    ids_obj = getattr(boxes, "id", None)
                    track_ids = ids_obj.int().cpu().tolist() if ids_obj is not None else [None] * len(xyxy)
                    for box, class_id, confidence, track_id in zip(xyxy, class_ids, confidences, track_ids):
                        class_name = CLASS_IDS.get(int(class_id))
                        if not class_name:
                            continue
                        detection_count += 1
                        overlay.append((box, class_name, float(confidence), track_id))
                        detections.append({"track_id": track_id, "class_name": class_name, "confidence": float(confidence),
                                           "frame_index": frame_index, "video_seconds": frame_index / fps,
                                           "bbox_xyxy": [round(float(value), 2) for value in box]})
                        minute = int((frame_index / fps) // 60)
                        counts_by_minute[minute]["total_detections"] += 1
                        if track_id is None:
                            continue
                        key = (int(track_id), class_name)
                        if key not in seen_tracks:
                            seen_tracks.add(key)
                            class_counts[class_name] += 1
                        counts_by_minute[minute]["tracks"].add(int(track_id))
                        center_x = (float(box[0]) + float(box[2])) / 2
                        old_x = previous_x.get(key)
                        if old_x is not None and key not in counted_tracks and ((old_x < line_x <= center_x) or (center_x < line_x <= old_x)):
                            counted_tracks.add(key)
                            crossing_count += 1
                            counts_by_minute[minute]["line_crossings"] += 1
                            counts_by_minute[minute]["class_counts"][class_name] += 1
                        previous_x[key] = center_x
            frame = frame.copy()
            cv2.line(frame, (int(line_x), 0), (int(line_x), height), (0, 210, 255), 2)
            for box, class_name, confidence, track_id in overlay:
                x1, y1, x2, y2 = [int(v) for v in box]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (30, 190, 105), 2)
                label = f"{class_name} {confidence:.2f}" + (f" · {track_id}" if track_id is not None else "")
                cv2.putText(frame, label, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, .5, (30, 190, 105), 1, cv2.LINE_AA)
            writer.write(frame)
            processed += 1
            if processed % 10 == 0:
                progress(processed, total_frames or max_frames)
        if processed == 0:
            raise ProcessingError("No decodable frames were found in the video.")
        metrics = []
        for minute, data in sorted(counts_by_minute.items()):
            metrics.append({"interval_start": job_created_at + timedelta(minutes=minute),
                            "interval_seconds": 60, "total_detections": data["total_detections"],
                            "unique_tracks": len(data["tracks"]),
                            "line_crossings": data["line_crossings"], "class_counts": dict(data["class_counts"]),
                            "count_direction": "screen_left_to_right_or_right_to_left"})
        note = "Processed first configured frame limit." if total_frames > processed else "Video processed frame by frame with configured sampling interval."
        progress(processed, total_frames or processed)
        return ProcessResult(detections, metrics, total_frames or processed, processed, detection_count,
                             len(seen_tracks), crossing_count, dict(class_counts), settings.model_path.name,
                             str(output_path), note)
    finally:
        capture.release()
        writer.release()
