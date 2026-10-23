from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import routes
from backend.database import Base, utc_now
from backend.models import Alert, Camera, ProcessingJob, TrafficMetric
from backend.seed_demo import seed_demo
from backend.services.analytics import active_data_mode, analytics_response, congestion_response, dashboard_overview
from backend.services.forecasting import create_forecast


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    engine.dispose()


def add_demo_metrics(db, count=1, demo=True):
    camera = Camera(camera_key="cam-test", name="Test Junction", location="Test District", status="configured", is_demo=demo)
    db.add(camera)
    db.flush()
    now = utc_now().replace(minute=0, second=0, microsecond=0)
    for offset in range(count):
        db.add(TrafficMetric(camera_id=camera.id, interval_start=now - timedelta(hours=offset), interval_seconds=3600,
                             total_detections=40, unique_tracks=20, line_crossings=20 + offset,
                             class_counts={"car": 12, "bus": 2, "motorcycle": 4, "truck": 2},
                             is_demo=demo, source="test"))
    db.commit()
    return camera


def test_api_routes_and_health_are_registered():
    from backend.main import app, dashboard, backend_ui_script
    app_paths = {getattr(route, "path", None) for route in app.routes}
    api_paths = {route.path for route in routes.router.routes}
    assert {"/api/health", "/api/dashboard/overview", "/api/jobs", "/api/reports/traffic.csv"} <= api_paths
    assert "/backend-ui.js" in app_paths
    assert routes.health()["status"] == "ok"
    assert dashboard().path.name == "index.html"
    assert backend_ui_script().path.name == "backend-ui.js"


def test_empty_state_is_explicit(db_session):
    db = db_session
    assert active_data_mode(db) == "empty"
    overview = dashboard_overview(db)
    assert overview["vehicles_counted"] is None
    assert overview["congestion_level"] == "unknown"
    assert analytics_response(db, "24h")["series"] == []
    result = create_forecast(db, 60)
    assert result["status"] == "insufficient_data"
    assert result["predicted_count"] is None


def test_seeded_demo_rows_do_not_enter_real_dashboard(db_session):
    add_demo_metrics(db_session, count=4)
    assert active_data_mode(db_session) == "empty"
    overview = dashboard_overview(db_session)
    assert overview["data_mode"] == "empty"
    assert overview["vehicles_counted"] is None
    assert overview["vehicle_classes"] == {}
    series = analytics_response(db_session, "24h")
    assert series["data_mode"] == "empty"
    assert series["series"] == []
    forecast = create_forecast(db_session, 60)
    assert forecast["status"] == "insufficient_data"
    assert forecast["predicted_count"] is None
    assert forecast["is_demo"] is False


def test_completed_video_jobs_drive_dashboard_counts(db_session):
    camera = add_demo_metrics(db_session, count=1, demo=False)
    job = ProcessingJob(id="video-job", original_filename="traffic.mp4", stored_path="video.mp4",
                        camera_id=camera.id, status="completed", unique_track_count=7,
                        crossing_count=4, class_counts={"car": 5, "bus": 2}, is_demo=False)
    db_session.add(job)
    db_session.commit()

    assert active_data_mode(db_session) == "processed_video"
    overview = dashboard_overview(db_session)
    assert overview["vehicles_counted"] == 7
    assert overview["vehicle_classes"] == {"car": 5, "bus": 2}
    assert analytics_response(db_session, "24h")["total_line_crossings"] == 20


def test_alert_acknowledgement_persists(db_session):
    add_demo_metrics(db_session)
    alert = Alert(alert_key="test-alert", severity="warning", title="Test alert", message="Test only", source="test", is_demo=True)
    db_session.add(alert)
    db_session.commit()
    result = routes.acknowledge_alert(alert.id, db_session)
    assert result.acknowledged_at is not None
    db_session.expire_all()
    assert db_session.get(Alert, alert.id).acknowledged_at is not None


def test_upload_container_signatures_and_csv_export(db_session):
    assert routes._valid_magic(".mp4", b"\x00\x00\x00\x18ftypisom")
    assert routes._valid_magic(".webm", b"\x1a\x45\xdf\xa3content")
    assert routes._valid_magic(".ogg", b"OggScontent")
    assert not routes._valid_magic(".mp4", b"not a video")
    add_demo_metrics(db_session)
    report = routes.report_csv(db_session)
    assert report.media_type.startswith("text/csv")
    assert b"Data mode,empty" in report.body
    assert b"Timestamp UTC" in report.body


def test_processing_model_status_does_not_claim_unconfigured_yolo():
    status = routes.model_status()
    assert status["downloads_automatic"] is False
    if not status["weights_found"]:
        assert status["ready"] is False



def test_congestion_uses_observed_camera_hour_rate(db_session):
    camera = add_demo_metrics(db_session, count=4, demo=False)
    result = congestion_response(db_session)
    zone = next(zone for zone in result["zones"] if zone["camera_id"] == camera.id)
    assert zone["flow_crossings_24h"] == 86
    assert zone["observed_hours"] == 4
    assert zone["flow_crossings_per_observed_hour"] == 21.5
    assert zone["level"] == "low"


def test_demo_seed_is_idempotent(db_session):
    first = seed_demo(db_session)
    second = seed_demo(db_session)
    assert first["metrics_added"] == 30 * 24 * 4
    assert second == {"cameras_added": 0, "alerts_added": 0, "metrics_added": 0}
