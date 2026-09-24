# Intermediate Concepts in the Project

This guide explains how the pieces cooperate, why the code uses them, and how to talk about the tradeoffs.

## 1. Application lifecycle

`vehicle_analytics/web.py` defines a FastAPI **lifespan** function. A lifespan function runs setup before the application accepts requests and cleanup when it shuts down.

The current startup order is:

1. `initialize_database()` creates the `detection_events` table if it is missing.
2. An `EventWriter` starts its database-writer thread.
3. A `PipelineRunner` starts its video-processing thread.
4. FastAPI begins serving the dashboard and API.

On shutdown, the application asks the pipeline to stop and then asks the writer to drain its queue and stop. Keeping this startup in one place makes the service easy to run with `python -m vehicle_analytics`.

## 2. The video pipeline

### Source selection

`PipelineRunner._resolve_source` converts a numeric string such as `"0"` to a camera index. A relative file path is checked against the current directory. URLs such as `rtsp://...` are passed to OpenCV as URLs.

`cv2.VideoCapture` opens the selected source. For a local file, `VIDEO_LOOP=true` seeks back to the first frame when it reaches the end. For a camera or URL, a failed read ends the current loop; it is not automatically reconnected.

### Detecting and tracking

The model is loaded once at pipeline startup:

```python
model = YOLO(settings.vehicle_model)
```

For each inference frame, the project calls:

```python
result = model.track(
    frame,
    persist=True,
    tracker="bytetrack.yaml",
    classes=[2, 3, 5, 7],
    conf=settings.confidence_threshold,
    imgsz=settings.inference_width,
    verbose=False,
)[0]
```

The call filters to the four supported COCO vehicle classes. `imgsz` controls the model inference size and `conf` is the minimum detection confidence. The first returned result is used because each call supplies one frame.

The result's `boxes.xyxy`, `boxes.id`, `boxes.cls`, and `boxes.conf` fields provide box coordinates, tracker IDs, class IDs, and confidence values. The code only counts or draws identified boxes when `boxes.id` is present. If a track ID is missing on a frame, that box is not fed to the line counter for that frame.

`INFERENCE_STRIDE` can skip inference on some frames. With the default `1`, every frame is sent to YOLO. Skipped frames are still read and, when output writing is enabled, copied to the annotated video without fresh annotations for that frame.

### Track IDs and sessions

ByteTrack IDs are temporary IDs from a running tracker. The pipeline creates a short random session ID at startup and forms IDs like `51a6b98bb6:75`. This reduces ambiguity when the source loops or the application restarts and track numbers are reused.

This is not a permanent real-world vehicle identity. If the tracker loses and redetects a car, it may receive a new track ID. The line counter can only de-duplicate events while the same track ID remains associated with that vehicle.

## 3. Line crossing with a deadband

The line position is `int(frame_height * COUNT_LINE_POSITION)`. For a 480-pixel-tall frame and ratio `0.55`, it is at y-coordinate 264.

`LineCounter` stores a `sides` dictionary mapping track ID to its last clear side:

- `-1`: above the line by more than the deadband
- `0`: within the deadband; do not change the remembered side
- `+1`: below the line by more than the deadband

If a track's remembered side changes from `-1` to `+1`, direction is `"down"`. A change from `+1` to `-1` gives `"up"`. After emitting one `Crossing`, the track ID is added to `counted`; later movement does not produce another event for that track in the same session.

Remembering the last clear side is important. A vehicle can move through several frames in the deadband. Comparing only consecutive frame positions could miss that gradual crossing.

## 4. Color calculation

The detector's bounding box is clipped to the frame boundaries before it is used as a NumPy slice. `classify_color` takes the central 60 percent of the crop to reduce road and background pixels. It converts this region from BGR to HSV with OpenCV.

The code first uses saturation to separate neutral colors from vivid colors. For a neutral crop it examines median brightness to choose white, silver, gray, or black. For a chromatic crop it uses median hue ranges for red, orange, yellow, green, blue, or purple.

This is a **heuristic**: a hand-designed rule based on pixel values. It is fast and does not require a second neural model, but it cannot robustly distinguish a car's paint from glass, reflection, shadow, or partial occlusion. There is no trained secondary color classifier in this implementation.

## 5. Non-blocking event persistence

Inference should not wait for a database insert on every crossing. `EventWriter.submit` creates an event payload and calls `put_nowait` on a bounded `queue.Queue`. The inference thread returns immediately instead of waiting for database latency.

The writer thread runs `_run`, removes one payload at a time, opens a SQLAlchemy session, adds a `DetectionEvent`, and commits it. The queue has a configurable maximum size (`EVENT_QUEUE_SIZE`, default 2000). If the queue is full, `submit` returns `False`, increments `dropped_events`, and logs the drop.

The current database-error behavior matters: a SQLAlchemy error is logged and stored in `last_error`, but that item is marked done and is not retried. The event can therefore be lost after a database failure. A more durable production design could add bounded retry rules or a persistent broker, but those are not part of this repository.

## 6. SQLAlchemy and the data model

`DetectionEvent` maps to `detection_events`. Its primary key `id` is an auto-incrementing database row number. `event_id` is a UUID string with a uniqueness constraint; it distinguishes event records. Indexed columns include `event_id`, `stream_name`, `vehicle_id`, `color`, `direction`, and `crossed_at`, helping common lookups and sorting.

`make_engine` uses the configured `DATABASE_URL`. SQLite gets `check_same_thread=False` because the app uses more than one thread. PostgreSQL URLs use the installed Psycopg driver, for example:

```text
postgresql+psycopg://vehicle_analytics:password@localhost:5432/vehicle_analytics
```

SQLAlchemy's `DateTime(timezone=True)` asks databases that support it to keep timezone information. `EventWriter` supplies a UTC timestamp with `datetime.now(timezone.utc)`. SQLite does not preserve timezone-aware timestamps in the same way PostgreSQL does, so an API timestamp read back from SQLite may not contain an explicit offset.

The schema is created with `Base.metadata.create_all`. This is convenient for a small project, but it is not a versioned migration system. Changing an existing table in a production deployment would need an explicit migration plan.

## 7. API and dashboard queries

`get_analytics` uses SQLAlchemy `select` expressions to fetch the total, today's count, grouped color counts, and the 20 newest events. The `/api/events` route independently selects the newest events and constrains `limit` to the range 1 to 500.

The dashboard is HTML produced by Jinja. Its `<meta http-equiv="refresh" content="5">` tag asks the browser to reload it every five seconds. This is simple polling through full-page reloads; there is no WebSocket or server-sent event stream.

`/api/health` returns an overall `status` value of `"ok"` plus detailed pipeline and writer status. The overall value is not a readiness calculation. To determine whether inference itself failed, inspect `pipeline.status` and `pipeline.error` in the response.

## 8. RTSP publishing path

`publish_rtsp.py` gets the FFmpeg executable from `imageio_ffmpeg`. Publishing launches FFmpeg with `-re` to read at the video's normal rate and `-stream_loop -1` to repeat the MP4. It encodes H.264 and sends the stream over RTSP/TCP to the provided URL.

MediaMTX's `traffic` path is configured to accept a publisher. `docker-compose.yml` maps RTSP port 8554, HLS 8888, and WebRTC 8889. The web dashboard does not embed any of those feeds; the endpoints make stream delivery available to other clients.

## 9. Configuration and command line

`config.py` reads environment variables after loading a project `.env` file. The `Settings` dataclass groups the values. Useful settings include:

| Setting | Effect |
|---|---|
| `VIDEO_SOURCE` | MP4 path, numeric camera index, or RTSP URL |
| `VIDEO_LOOP` | Rewind local files at end of input |
| `VEHICLE_MODEL` | Ultralytics model file or model name |
| `CONFIDENCE_THRESHOLD` | Detection confidence cutoff |
| `INFERENCE_WIDTH` | YOLO inference image size |
| `INFERENCE_STRIDE` | Run inference once every N frames |
| `COUNT_LINE_POSITION` | Horizontal line as a fraction of frame height |
| `DATABASE_URL` | SQLite or PostgreSQL connection URL |
| `SAVE_ANNOTATED_VIDEO` | Write annotated output to disk |

`python -m vehicle_analytics` starts the web application and pipeline. The optional `publish-rtsp` and `probe-rtsp` commands use the same module entry point.

## 10. Concurrency and shared state

The pipeline and event writer each run in their own Python daemon thread. The pipeline's status snapshot is read by the API while the pipeline updates it, so `state_lock` guards those status fields. The event queue is thread-safe by design. The writer counters are simple values read by health requests; they are not protected by a dedicated lock.

The database work is synchronous inside the writer thread. This keeps database calls off the inference loop without requiring asynchronous database drivers.
