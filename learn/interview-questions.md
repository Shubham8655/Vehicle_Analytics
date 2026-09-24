# Project Interview Questions

These questions and answers are based on the implementation in this repository. The answers use simple English while retaining the technical terms interviewers expect.

## Easy — 10 questions

### 1. What does this project do?

It reads a traffic video or camera stream, detects cars, motorcycles, buses, and trucks, tracks them over time, estimates their color, and records an event when a track crosses a horizontal line. A FastAPI dashboard shows the saved totals and recent crossings.

### 2. What is the difference between object detection and object tracking?

Object detection finds objects in one frame and returns bounding boxes, class labels, and confidence scores. Object tracking tries to match those detections from one frame to the next and keeps a temporary ID for each object. This project uses YOLO for detection and ByteTrack for tracking.

### 3. Which vehicle classes does the detector keep?

The pipeline filters the COCO model results to class IDs 2, 3, 5, and 7: car, motorcycle, bus, and truck. It ignores other COCO classes such as people and bicycles.

### 4. What is a bounding box?

A bounding box is a rectangle around a detected object. This code represents it with `(x1, y1, x2, y2)`, meaning the top-left and bottom-right coordinates. The project uses this rectangle both to draw the detection and to crop vehicle pixels for color estimation.

### 5. How does the application decide that a vehicle crossed the line?

It calculates the vertical center of the vehicle's bounding box and compares it with a horizontal line at `COUNT_LINE_POSITION` of the frame height. The line counter remembers the last clear side for each track. When the track reaches the clear opposite side, it reports `up` or `down`. A deadband around the line helps ignore small detection jitters.

### 6. How is vehicle color estimated?

The application takes the middle of the vehicle crop, changes pixel values from BGR to HSV, and uses median hue, saturation, and brightness values to choose a coarse label. This is a simple rule-based estimate; it is not a trained color classifier and can be wrong in shadows or reflections.

### 7. What information is stored for a crossing?

The `detection_events` table stores a unique UUID event ID, stream name, session-qualified vehicle ID, class, estimated color, crossing direction, detection confidence, and timestamp. The event timestamp is created when the application submits the crossing to its writer queue.

### 8. Why does the project support both SQLite and PostgreSQL?

SQLite is a database stored in a local file, so it makes the application easy to start without another service. PostgreSQL is a database server that can be shared by multiple application instances. SQLAlchemy lets the same Python table model work with both; configure the choice with `DATABASE_URL`.

### 9. What is FastAPI used for?

FastAPI serves the dashboard and the HTTP API. For example, `GET /api/stats` returns aggregate counts as JSON, and `GET /api/events` returns recent saved rows. The `/` route renders HTML using Jinja templates.

### 10. How can someone run the sample locally?

Create and activate a Python virtual environment, install `requirements.txt`, copy `.env.example` to `.env`, then run `python -m vehicle_analytics`. Open `http://127.0.0.1:8000`. The application uses `traffic.mp4` and SQLite by default. The first run may download the YOLO model weights.

## Medium — 10 questions

### 1. Why use a tracker if the detector already finds vehicles?

The detector works frame by frame. Without tracking, a car could be treated as unrelated detections in every image, making line-crossing counts repeat. ByteTrack associates detections across frames and provides IDs. The counter uses those IDs to remember crossing state and emit no more than one event per track in its session. If the tracker loses and recreates an ID, the application can still count that as another track.

### 2. What does `persist=True` do in the model call?

It tells Ultralytics to keep tracker state between `model.track` calls. The pipeline invokes the model once per inference frame. Without persistent state, the tracker would not be able to maintain IDs from one call to the next.

### 3. Why is there a deadband around the counting line?

Detections can move a few pixels from frame to frame even when the vehicle has not meaningfully crossed. The deadband gives a neutral area around the line. The counter remembers the last clear side while a track is in that area and only counts after it reaches a clear position on the other side.

### 4. Why put database writes on a separate thread?

Database commits can take longer than video processing. If the inference loop waited for each commit, it could process fewer frames. `EventWriter.submit` adds a payload to a bounded queue without waiting; its own thread takes events from the queue and commits them. The tradeoff is that this queue is in memory and is not durable.

### 5. What happens when the event queue fills up?

`put_nowait` raises `queue.Full`. The writer records a dropped-event count, logs an error, and returns `False`. The inference loop can continue, but that particular event is lost. `/api/health` reports the queue depth and drop count.

### 6. How does the project create a useful vehicle ID?

ByteTrack produces temporary numeric IDs. The pipeline adds a short random session identifier, forming a string such as `51a6b98bb6:75`. This avoids collisions when tracker IDs start over after an application restart. It does not identify a physical car permanently.

### 7. How does `INFERENCE_STRIDE` affect the pipeline?

It controls how many frames are skipped between model inferences. At `1`, every frame gets an inference. At `5`, the model runs on every fifth frame. A larger stride can reduce computation, but gives the tracker fewer observations and can make it miss short events or lose associations.

### 8. How does the dashboard get its values, and is it truly pushed live?

The FastAPI route queries the database for totals, counts grouped by color, and newest events, then Jinja renders the page. A five-second HTML meta refresh reloads the whole page. Data is not pushed over WebSockets or server-sent events.

### 9. What is the role of MediaMTX and FFmpeg?

MediaMTX is an optional stream server. The project's FFmpeg command can publish the MP4 repeatedly to its RTSP path over TCP. OpenCV can then read the RTSP URL. For the default local run, OpenCV reads the MP4 directly and neither MediaMTX nor RTSP is required.

### 10. How does the database configuration switch between SQLite and PostgreSQL?

The code reads `DATABASE_URL` into settings and passes it to SQLAlchemy's `create_engine`. For SQLite, it adds `check_same_thread=False` because the application uses multiple threads. A PostgreSQL URL uses the Psycopg driver, for example `postgresql+psycopg://user:password@host:5432/database`.

## Difficult — 5 questions

### 1. What are the main reliability risks in the current event persistence design?

The queue is bounded and stored only in memory. If it fills, new events are dropped. If the process exits before the writer commits queued events, those pending events disappear. If a database insert raises `SQLAlchemyError`, the writer logs the error and sets `last_error`, but it still marks the queue item complete; it does not retry or send the event to a dead-letter store. To improve reliability, I would add a clear retry policy with backoff and durable buffering, then test behavior during a database outage. Those improvements are not currently implemented.

### 2. Can the current system guarantee that one physical vehicle is counted exactly once?

No. It guarantees at most one count per tracker ID inside the current pipeline session. If ByteTrack loses a vehicle and later assigns it a new ID, that physical vehicle could generate a second event. Conversely, if the vehicle is never detected on both clear sides of the line, it may not be counted. A true physical-vehicle identity guarantee would require stronger association logic and careful camera/scene assumptions; it is not a feature of this code.

### 3. What makes the color output less reliable than the detector class?

The detector is a trained neural model, while color is a hand-designed heuristic over pixels in a box. A box can contain windows, road, shadows, reflections, or another object. Lighting changes hue and brightness. The code reduces background influence by looking at the center crop and uses medians, but that only helps; it does not guarantee correct paint color. A stronger approach would train or integrate a vehicle-color classifier and evaluate it on labeled examples from the target camera. That classifier is not present here.

### 4. How would you scale the project to many cameras?

The current application creates one pipeline runner from one `VIDEO_SOURCE` setting, so it is a single-source design. To support multiple sources, I would first give each source its own capture and tracker state, and ensure each event records the source identity. I would measure inference throughput and database queue behavior before deciding whether to use separate worker processes or GPU batching. The existing queue is process-local, so scaling across processes would need a shared message broker or another durable handoff. Those multi-camera capabilities are design ideas, not implemented features.

### 5. The assignment mentions DeepStream. What does this project actually use, and what would change for DeepStream?

This repository does not contain a DeepStream pipeline. It uses Python OpenCV capture, Ultralytics YOLO detection, and ByteTrack association because the working environment is Windows and the implementation was kept Python-only. A DeepStream version would need to run in a supported NVIDIA Linux environment and would replace the capture/inference/tracker path with GStreamer and DeepStream elements, while preserving an equivalent event schema and downstream database/API behavior. The current code does not provide those DeepStream elements or configuration.
