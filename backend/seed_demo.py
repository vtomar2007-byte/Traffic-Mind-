"""Idempotent demo fixtures; every inserted row is explicitly marked is_demo."""
from __future__ import annotations

import argparse
import math
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import SessionLocal, init_db, utc_now
from backend.models import Alert, Camera, TrafficMetric

CAMERAS = [
    ("cam-central", "Central Junction", "Central District", 28.6139, 77.2090, "sample"),
    ("cam-north", "North Avenue", "North District", 28.6300, 77.2200, "sample"),
    ("cam-river", "Riverside Road", "River District", 28.6000, 77.1900, "sample"),
    ("cam-south", "South Gate", "South District", 28.5900, 77.2150, "unavailable"),
]


def seed_demo(session: Session) -> dict[str, int]:
    now = utc_now().replace(minute=0, second=0, microsecond=0)
    cameras_added = alerts_added = metrics_added = 0
    cameras = {}
    for key, name, location, lat, lon, status in CAMERAS:
        camera = session.scalar(select(Camera).where(Camera.camera_key == key))
        if camera is None:
            camera = Camera(camera_key=key, name=name, location=location, latitude=lat,
                            longitude=lon, status=status, is_demo=True)
            session.add(camera)
            session.flush()
            cameras_added += 1
        cameras[key] = camera

    demo_alerts = [
        ("demo-central-congestion", "critical", "Heavy congestion at Central Junction", "Illustrative count above the demo threshold.", "cam-central", False),
        ("demo-north-speed", "warning", "Sample flow below the demo baseline", "Illustrative sample alert; no speed was measured.", "cam-north", False),
        ("demo-south-camera", "info", "Demo camera status is unavailable", "This is a seeded status example, not a connected camera.", "cam-south", True),
    ]
    for key, severity, title, message, camera_key, acknowledged in demo_alerts:
        if session.scalar(select(Alert.id).where(Alert.alert_key == key)) is None:
            session.add(Alert(alert_key=key, severity=severity, title=title, message=message,
                              source="demo-seed", camera_id=cameras[camera_key].id,
                              supporting_metrics={"data_mode": "demo"}, is_demo=True,
                              acknowledged_at=now if acknowledged else None))
            alerts_added += 1

    class_shares = {"car": .58, "motorcycle": .21, "bus": .09, "truck": .12}
    start_interval = now - timedelta(hours=30 * 24)
    camera_ids = [camera.id for camera in cameras.values()]
    existing_metrics = set(session.execute(select(TrafficMetric.camera_id, TrafficMetric.interval_start).where(
        TrafficMetric.is_demo.is_(True), TrafficMetric.camera_id.in_(camera_ids),
        TrafficMetric.interval_start >= start_interval)).all())
    for hour_index in range(30 * 24):
        interval = now - timedelta(hours=30 * 24 - hour_index)
        hour = interval.hour
        rush = 1.0 + .65 * math.exp(-((hour - 8) / 2.2) ** 2) + .9 * math.exp(-((hour - 17) / 2.4) ** 2)
        for camera_index, (camera_key, *_rest) in enumerate(CAMERAS):
            camera = cameras[camera_key]
            marker = (camera.id, interval)
            if marker in existing_metrics:
                continue
            count = int((20 + camera_index * 8) * rush + 8 * math.sin((hour_index + camera_index) * .37) + 13)
            count = max(0, count)
            classes = {name: round(count * share) for name, share in class_shares.items()}
            classes["car"] += count - sum(classes.values())
            session.add(TrafficMetric(camera_id=camera.id, interval_start=interval,
                                      interval_seconds=3600, total_detections=count * 2,
                                      unique_tracks=count, line_crossings=count,
                                      class_counts=classes, count_direction="demo aggregate",
                                      is_demo=True, source="demo-seed"))
            existing_metrics.add(marker)
            metrics_added += 1
    session.commit()
    return {"cameras_added": cameras_added, "alerts_added": alerts_added, "metrics_added": metrics_added}


def main() -> None:
    parser = argparse.ArgumentParser(description="Add missing repeatable TrafficMind demo fixtures.")
    parser.parse_args()
    init_db()
    with SessionLocal() as session:
        counts = seed_demo(session)
    print("Demo seed complete (idempotent; no records removed): " + ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
