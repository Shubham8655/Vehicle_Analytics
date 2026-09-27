# Real-Time Vehicle Analytics Pipeline

Python vehicle analytics for a traffic video or RTSP camera. The service detects vehicles, maintains track IDs, estimates body color, counts each tracked vehicle the first time it crosses a configurable line, stores that event, and serves a responsive dashboard and JSON API.

## Architecture

```text
traffic.mp4 / live camera
         │
         ├── optional Python FFmpeg publisher ── RTSP ── MediaMTX
         │                                             │
         └─────────────────────────────────────────────┘
                          │
               OpenCV video capture
                          │
         Ultralytics YOLO COCO vehicle detections
                          │
                ByteTrack track association
                          │
           HSV color estimate + line crossing
                          │
             bounded event queue / writer thread
                          │
          PostgreSQL (or local SQLite by default)
                          │
             FastAPI + Python/Jinja dashboard
```

The inference implementation is Python-first and runs on Windows, Linux, or macOS. DeepStream is an NVIDIA Linux platform and is not available in this Windows environment; this project uses Ultralytics YOLO and ByteTrack through Python instead. The interface and event schema leave the ingestion and inference components separable for a future DeepStream deployment.

## Requirements

- Python 3.10 or later (Python 3.11 recommended)
- `traffic.mp4` for the included sample run
- Optional: Docker Desktop with Docker Compose for PostgreSQL and MediaMTX
- Optional: an NVIDIA GPU and compatible PyTorch/CUDA installation for accelerated inference

FFmpeg is bundled by the `imageio-ffmpeg` Python dependency; no separate FFmpeg installation is needed for RTSP publishing or probing. YOLO weights download from Ultralytics on the first pipeline start. The app defaults to SQLite so it can run without PostgreSQL or Docker.

## Quick start

In PowerShell from the project directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
clear
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The application starts the dashboard, database schema, background writer, and video pipeline. The first start downloads the configured YOLO model weights. The annotated output is written to `runs/annotated.mp4` by default.

Run with another video or camera:

```powershell
$env:VIDEO_SOURCE = "D:\Elansol project\Vehicle_Analytics\traffic.mp4"
python -m vehicle_analytics

$env:KMP_DUPLICATE_LIB_OK="TRUE" " for duplicates error"
``` 

`VIDEO_SOURCE` accepts a file path, camera device number such as `0`, or a URL such as `rtsp://127.0.0.1:8554/traffic`. For a live camera, set `VIDEO_LOOP=false`.

## PostgreSQL and MediaMTX

The included Compose file starts both services with persistent PostgreSQL storage:

```powershell
docker compose up -d postgres mediamtx
```

Configure `.env` for PostgreSQL and the local RTSP endpoint:

```dotenv
DATABASE_URL=postgresql+psycopg://vehicle_analytics:vehicle_analytics@127.0.0.1:5432/vehicle_analytics
VIDEO_SOURCE=rtsp://127.0.0.1:8554/traffic
VIDEO_LOOP=false
```

Publish the supplied MP4 to MediaMTX in a second terminal:

```powershell
python -m vehicle_analytics publish-rtsp --source traffic.mp4 --url rtsp://127.0.0.1:8554/traffic
```

Probe the RTSP endpoint:

```powershell
python -m vehicle_analytics probe-rtsp --url rtsp://127.0.0.1:8554/traffic
```

MediaMTX exposes RTSP on port 8554, HLS on 8888, and WebRTC on 8889. If Docker Desktop is unavailable, run the app with its SQLite default and point `VIDEO_SOURCE` directly at `traffic.mp4` or a camera URL.

## Dashboard and API

- `/` — server-rendered responsive dashboard, refreshes every five seconds
- `/api/health` — pipeline, event writer, and database health
- `/api/stats` — aggregate crossing counts and color breakdown
- `/api/events?limit=50` — most recent persisted events (limit 1–500)

## Pipeline decisions

- **Vehicle detector:** configurable Ultralytics COCO checkpoint (`yolo11n.pt` by default), filtered to car, motorcycle, bus, and truck classes.
- **Tracking:** Ultralytics' persistent ByteTrack association (with `lap` assignment support) keeps IDs across video frames. Each track gets a session-qualified ID, so IDs do not collide after looping or restarting the source.
- **Color:** a coarse HSV estimate from the center of each vehicle crop. This is intentionally lightweight; lighting, paint finish, occlusion, and crop size affect the estimate.
- **Counting:** horizontal line at `COUNT_LINE_POSITION` of frame height, with a deadband to damp jitter. A track can emit one crossing event per pipeline session; event IDs are UUIDs.
- **Persistence:** inference submits events to a bounded, non-blocking queue. A dedicated writer thread performs database inserts so slow storage does not hold up frame processing. Queue saturation is reported as dropped events in `/api/health`.
- **Storage:** SQLAlchemy creates the same `detection_events` schema in PostgreSQL and SQLite. The table stores stream, session-qualified vehicle ID, vehicle class, color, direction, confidence, UUID event ID, and crossing timestamp.
- **Dashboard:** FastAPI and Jinja render HTML in Python; no Node/React build is required. The JSON endpoints can support a separate UI if needed.

### Configuration

Copy `.env.example` to `.env`; settings are also configurable as environment variables.

| Setting | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | local SQLite | SQLAlchemy URL for PostgreSQL or SQLite |
| `VIDEO_SOURCE` | `traffic.mp4` | File, camera index, or RTSP URL |
| `VIDEO_LOOP` | `true` | Loop local files at end of input |
| `STREAM_NAME` | `traffic-camera-01` | Source name stored with events |
| `VEHICLE_MODEL` | `yolo11n.pt` | Ultralytics model path or checkpoint |
| `CONFIDENCE_THRESHOLD` | `0.35` | Detection confidence cutoff |
| `INFERENCE_WIDTH` | `640` | YOLO inference image size |
| `INFERENCE_STRIDE` | `1` | Run inference every Nth frame |
| `COUNT_LINE_POSITION` | `0.55` | Count line as a fraction of frame height |
| `SAVE_ANNOTATED_VIDEO` | `1` | Save annotated output video |

## Verification

Run the unit and API smoke tests:

```powershell
python -m unittest discover -s tests -v
```

The checks cover line-crossing direction and de-duplication, color labels, schema creation on SQLite, dashboard rendering, and the JSON endpoints. A real inference run also requires downloading YOLO weights on first use.

## Repository contents

- `vehicle_analytics/` — pipeline, persistence, configuration, dashboard and RTSP utilities
- `vehicle_analytics/templates/` — responsive server-rendered dashboard
- `docker-compose.yml`, `mediamtx.yml` — optional PostgreSQL and MediaMTX services
- `tests/` — Python unit and API smoke tests
- `traffic.mp4` — provided sample input
