# TrafficMind

TrafficMind is a local-first student project for traffic video analytics and prediction. The dashboard retains the original HTML/CSS/JavaScript interface. The local sample video is intentionally excluded from GitHub; the dashboard and upload workflow work without it. A small FastAPI service adds local persistence, analytics endpoints, baseline forecasts, alerts, CSV reports, and an optional YOLO/ByteTrack video-processing path.

All seeded values are marked as **demo data**. Processing results come only from videos explicitly submitted to the local API. They describe the analyzed clip and virtual counting line; they are not live camera feeds, calibrated speed measurements, or city-wide traffic statistics. Forecasts are moving-average baselines, not AI predictions.

## Requirements

- Windows 10/11
- Python 3.11 or 3.12 (64-bit recommended)
- Browser with HTML5 video support
- Git is optional for running the project

The static dashboard still opens with a double-click on `index.html`. The local API, database persistence, alert acknowledgement, API reports, and video analysis require the server described below. No Node.js/npm is required. SQLite is included through Python dependencies.

## Setup on Windows

Open PowerShell in the repository directory. If Python is not installed, install Python 3.12 from python.org, enable the launcher/PATH option, and reopen PowerShell. Check with `py -3.12 --version`.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
.\run.ps1
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The first server start creates a local SQLite database in `data/` and shows an empty analytics state until a video is analyzed. Existing seeded demo rows are preserved in the database but are not used for dashboard results. Keep the server window open; stop it with `Ctrl+C`. The virtual environment, database, uploaded videos, and generated previews are local and ignored by Git.

For manual setup, run these commands from the project root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

If the `py` launcher is unavailable but `python` works, use `python` in place of `py -3.12`. `setup.ps1` checks both options and installs only into the project `.venv`. Do not run PowerShell as administrator.

## Dashboard behavior

- **Overview, Live Monitoring, Analytics, Predictions, Congestion Map, Alerts, System:** dashboard navigation and accessible keyboard controls.
- **Analytics:** hourly persisted line crossings and class totals; date ranges can have sparse buckets because video observations are not extrapolated into missing data.
- **Forecast:** transparent three-bucket moving-average baseline. Real video-derived history is considered insufficient until there are at least 24 hourly buckets spanning three dates. MAE/RMSE are not reported because a held-out evaluation set is not included.
- **Congestion:** configurable virtual-line crossing thresholds are a flow proxy, not measured road density or speed.
- **Local preview:** choose a video from this device for browser-only preview, even when the optional bundled sample is absent. With the API running, analysis is enabled only if optional ML dependencies and local weights are configured. Choosing **Analyze locally** sends the selected file only to this local API. Uploads are limited by `TRAFFICMIND_MAX_UPLOAD_MB` (default 150 MB), and sampled processing is bounded by `TRAFFICMIND_MAX_VIDEO_FRAMES` (default 3000).
- **CSV:** with the API connected, the CSV is generated from persisted video-analysis results. Direct-file mode exports a clearly labeled empty-state report.
- **Optional local sample:** if `assets/traffic.mp4` is available on this computer, **Process optional sample** can analyze it. Video files are ignored by Git, so this sample is absent from a fresh clone. Otherwise, choose a video from your device; the sample action stays disabled when its file is absent.

If the API is unavailable, the interface shows an empty analytics state. Preview a video selected from your device; the optional sample may be absent. It does not substitute sample values. The API status appears in the System section.

## Optional local vehicle detection

The core installation does not install PyTorch, OpenCV, YOLO, or model weights. For CPU-only Windows inference, install PyTorch from its CPU wheel index, then install the optional OpenCV and Ultralytics requirements:

```powershell
.\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
```

To enable the bundled COCO-compatible YOLO11n weights, download the official Ultralytics asset locally; the file is ignored by Git and is never uploaded by TrafficMind:

```powershell
New-Item -ItemType Directory -Force models | Out-Null
Invoke-WebRequest -Uri https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt -OutFile models/trafficmind.pt
```

Alternatively, set `TRAFFICMIND_MODEL_PATH` in `.env` to an existing local weights file. No weights download occurs automatically. Vehicle KPIs count unique tracked objects from completed videos; time-series charts, congestion proxies, and threshold alerts use actual virtual-line crossings. The implementation filters COCO classes `car`, `motorcycle`, `bus`, and `truck` and uses ByteTrack IDs. Speed is not estimated. The model's accuracy has not been evaluated by this project; validate it against a labeled dataset before using the results beyond a demo.

## Configuration

Copy `.env.example` to `.env` to adjust local settings. Defaults bind the server to `127.0.0.1` and use SQLite in `data/`. Do not put secrets in `.env.example` or commit `.env`. The server exposes no authentication and is intended for local development only; do not bind it to a public interface or expose it to the internet.

Important options: `TRAFFICMIND_DATABASE_URL`, `TRAFFICMIND_DATA_DIR`, `TRAFFICMIND_MODEL_PATH`, `TRAFFICMIND_MAX_UPLOAD_MB`, `TRAFFICMIND_MAX_VIDEO_FRAMES`, `TRAFFICMIND_PROCESS_EVERY_N_FRAMES`, `TRAFFICMIND_CONFIDENCE`, and `TRAFFICMIND_COUNT_LINE_RATIO`. Use a fresh backup before manually changing a database URL. This student milestone uses SQLAlchemy `create_all`; it does not include schema migration tooling.

## API reference

Interactive local API docs are available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) while the server is running. Main endpoints:

- `GET /api/health`, `GET /api/ready`, `GET /api/system/status`
- `GET /api/dashboard/overview`, `GET /api/cameras`, `POST /api/cameras`
- `GET /api/analytics/traffic?range=24h|7d|30d`, `GET /api/congestion`
- `POST /api/forecasts`, `GET /api/forecasts`
- `GET /api/alerts`, `PATCH /api/alerts/{id}/acknowledge`
- `POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`, `DELETE /api/jobs/{id}`
- `GET /api/jobs/{id}/preview`, `GET /api/reports/traffic.csv`

## Tests and troubleshooting

Run the API and data tests with:

```powershell
.\test.ps1
```

If the browser is opened directly from `index.html`, local preview and navigation work, but the API is not queried and the dashboard stays empty. For local video analysis, use the `127.0.0.1:8000` address. If a port conflict occurs, stop the other local process or change the port in `.env` and `run.ps1`. If the bundled MP4 does not play in a browser, try another H.264 MP4 clip; codec support depends on the browser and installed media components.

## Project structure

```text
backend/                 FastAPI application, SQLAlchemy models, analytics, forecasts, video jobs
backend/api/             REST endpoints, upload validation, CSV export
backend/services/        detection, analytics, forecast, background job orchestration
assets/README.md        Notes for the optional, locally ignored sample video
index.html               Existing dashboard markup
app.js, styles.css       Existing dashboard interactions and styles
api-client.js            Same-origin API helper
backend-ui.js            Progressive API-backed dashboard integration
setup.ps1, run.ps1       Windows-local environment setup and server launch
test.ps1, tests/          Local checks and test suite
requirements*.txt        Core, development, and optional ML dependency sets
```

## Current limitations and next steps

This is a single-user local student app. It has no login, role management, live camera/RTSP ingest, model training, dataset labels, model accuracy evaluation, migrations, or production deployment configuration. SQLite and a single background worker are suitable for a demo, not concurrent production traffic. Next, collect/document a lawful dataset, evaluate detection and forecasting against held-out labels, add migrations and authentication, then consider a production database and deployment controls.
