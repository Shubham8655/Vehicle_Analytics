# Project Basics

This guide introduces the main ideas and tools used in this repository. It assumes you are new to computer vision and web applications, but keeps the real technical names so you can use them in an interview.

## 1. What the project does

The application reads a traffic video, finds vehicles in each frame, tries to keep the same ID attached to each vehicle as it moves, estimates a rough body color, and records an event when a tracked vehicle crosses a horizontal line. A small web server shows the saved counts and recent events.

The normal local run uses `traffic.mp4` and SQLite. PostgreSQL and MediaMTX are optional services defined in Docker Compose. The video may also be sent through MediaMTX using RTSP, but the pipeline can read a video file or RTSP URL directly.

## 2. A few Python building blocks

### Variables and values

A variable is a name that refers to a value:

```python
line_y = 264
stream_name = "traffic-camera-01"
```

Here, `line_y` is an integer pixel coordinate and `stream_name` is text. The project uses values like these to configure the video source and counting line.

### Functions

A function groups steps under a name. It can accept inputs and return a result:

```python
def classify_color(crop):
    if crop.size == 0:
        return "unknown"
```

In this project, `classify_color` receives a small image crop and returns a simple label such as `"blue"` or `"silver"`.

### Classes and objects

A class describes an object that keeps related data and behavior together. An object is one instance of that class.

```python
counter = LineCounter(line_y=264, session_id="abc123")
```

The `LineCounter` object remembers which side of the line it last saw each tracker ID on. This memory lets it tell a crossing from a vehicle that is simply visible near the line.

### Dictionaries



A dictionary maps keys to values:

```python
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
```

The detector returns COCO class numbers. This dictionary translates the four class numbers accepted by the pipeline into readable names.

### Type hints

A type hint documents what kind of value is expected or returned:

```python
def update(self, track_id: int, center_y: int) -> Crossing | None:
    ...
```

This says that `track_id` and `center_y` are integers, and the method returns either a `Crossing` object or `None`. `None` means no crossing happened on that update. Type hints help readers and code editors; Python does not enforce every hint at runtime.

### Environment variables

Environment variables let a user change settings without editing the source code. For example, `VIDEO_SOURCE` selects the input and `DATABASE_URL` selects the database. The `.env.example` file lists common values. A local `.env` file can override defaults and is excluded from Git.

## 3. Video and computer vision

### Frames and pixels

A video is a sequence of still images called **frames**. OpenCV reads a frame into a NumPy array. Each pixel stores color values. OpenCV normally represents images as BGR: blue, green, red channel order.

The sample video is 854 pixels wide and 480 pixels high. Coordinates start near the top-left corner: `x` increases to the right and `y` increases downward.

### Object detection

**Object detection** means finding objects in one image and returning a rectangle and a class for each object. The rectangle is often called a **bounding box**. In this project it is represented by `(x1, y1, x2, y2)`, the top-left and bottom-right corners.

The project uses an Ultralytics YOLO model with COCO classes. YOLO is a family of neural-network object detectors. COCO is a dataset with common object categories. The pipeline keeps these COCO IDs:

| COCO ID | Name used in the project |
|---:|---|
| 2 | car |
| 3 | motorcycle |
| 5 | bus |
| 7 | truck |

Each detection also has a **confidence score**, a number indicating how certain the model is. The default cutoff is `0.35`, so lower-confidence detections are filtered out.

### Tracking

Detection is repeated frame by frame. Without tracking, the same car could look like a new object in every frame. A **multi-object tracker** links detections over time and assigns a temporary track ID.

This project calls Ultralytics `model.track(..., persist=True, tracker="bytetrack.yaml")`. ByteTrack is the tracking algorithm. `persist=True` tells the model to keep tracker state between calls. A track ID is only meaningful inside that tracker session; the project prefixes it with a generated session ID before saving it.

### Color estimation

The pipeline crops the detected vehicle rectangle and calls `classify_color`. This is a lightweight computer-vision rule, not a separate trained color model. The function converts BGR pixels into **HSV** (hue, saturation, value):

- **Hue** roughly represents the color family, such as red or blue.
- **Saturation** represents how vivid or gray a color looks.
- **Value** represents brightness.

It examines the middle part of the crop to reduce pixels from the road and background, then uses median values to choose labels such as red, orange, yellow, green, blue, purple, white, silver, gray, or black. Lighting, shadows, small vehicles, and mixed paint can make this estimate wrong.

## 4. Counting a line crossing

The count line is horizontal. Its vertical position is calculated from frame height. With the default `COUNT_LINE_POSITION=0.55` and 480-pixel frame height, the line is near `y=264`.

For each tracked vehicle, the pipeline uses the vertical center of its bounding box:

```python
center_y = (y1 + y2) // 2
crossing = counter.update(track_id, center_y)
```

The counter remembers the last clear side of the line for each track. A small **deadband** around the line ignores tiny position changes caused by detector jitter. When a track is first seen clearly on one side and later clearly on the other, the counter returns a direction (`"down"` or `"up"`). Each track is counted at most once in that pipeline session.

## 5. Saving events

An event is one recorded line crossing. It contains a UUID event ID, stream name, session-qualified vehicle ID, vehicle class, color, direction, confidence, and timestamp.

**SQLite** is a small database stored in a file. It is the default so the project can run without installing a database server. **PostgreSQL** is a separate database server suited to multi-user or production deployments. The same SQLAlchemy table model is used with either database.

**SQLAlchemy** is an ORM (object-relational mapper). It maps Python classes to database tables. `DetectionEvent` is the Python class for the `detection_events` table.

## 6. Web dashboard and API

**FastAPI** is the Python web framework. A route connects a URL and HTTP method to Python code:

```python
@app.get("/api/stats")
def stats():
    ...
```

This route answers a `GET /api/stats` request with JSON statistics. The `/` route renders HTML using **Jinja**, a template engine. The page refreshes every five seconds; it does not use a JavaScript live-update connection.

Useful URLs after starting the app:

- `/` — dashboard
- `/api/health` — pipeline and writer status
- `/api/stats` — counts and color totals
- `/api/events?limit=50` — latest saved events

## 7. RTSP, FFmpeg, and MediaMTX

**RTSP** is a network protocol commonly used to publish and read live video. **FFmpeg** is a media tool used here to read the MP4 and publish a repeating video stream. **MediaMTX** is the optional media server that accepts the published RTSP stream and can expose it through RTSP, HLS, or WebRTC.

The `publish-rtsp` command uses FFmpeg bundled by the Python package `imageio-ffmpeg`. RTSP publishing is optional: for a simple local run, OpenCV reads `traffic.mp4` directly.

## 8. Docker Compose

**Docker** runs software in containers, which package an application with a predictable runtime. **Docker Compose** describes and starts multiple containers together. This project's `docker-compose.yml` defines a PostgreSQL container and a MediaMTX container. Docker is not required for the default SQLite run.

## 9. Main project files

| File | Purpose |
|---|---|
| `vehicle_analytics/pipeline.py` | Reads frames, runs detection/tracking, draws annotations, detects crossings |
| `vehicle_analytics/counting.py` | Tracks each object's side of the count line |
| `vehicle_analytics/colors.py` | Estimates color from HSV pixels |
| `vehicle_analytics/persistence.py` | Queues and writes crossing events on a background thread |
| `vehicle_analytics/database.py` | SQLAlchemy table and database engine |
| `vehicle_analytics/web.py` | FastAPI lifecycle, dashboard, and JSON endpoints |
| `vehicle_analytics/templates/dashboard.html` | Server-rendered dashboard markup and styles |
| `vehicle_analytics/config.py` | Environment-based settings |
| `vehicle_analytics/publish_rtsp.py` | Optional RTSP publishing and probing commands |
| `docker-compose.yml`, `mediamtx.yml` | Optional PostgreSQL and MediaMTX setup |
| `tests/test_core.py` | Python tests for counting, colors, persistence, and API responses |
