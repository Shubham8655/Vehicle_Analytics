"""OpenCV + Ultralytics detection, ByteTrack association and line counting."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from pathlib import Path

import cv2
from ultralytics import YOLO

from .colors import classify_color
from .config import settings
from .counting import LineCounter
from .persistence import EventWriter

logger = logging.getLogger(__name__)
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


class PipelineRunner:
    def __init__(self, writer: EventWriter):
        self.writer = writer
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.state_lock = threading.Lock()
        self.status = "stopped"
        self.error: str | None = None
        self.frames_processed = 0
        self.last_frame_at: float | None = None
        self.session_id: str | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self.run, name="vehicle-pipeline", daemon=True)
        self.thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=timeout)

    def snapshot(self) -> dict:
        with self.state_lock:
            return {
                "status": self.status,
                "error": self.error,
                "frames_processed": self.frames_processed,
                "last_frame_at": self.last_frame_at,
                "session_id": self.session_id,
                "source": settings.video_source,
                "model": settings.vehicle_model,
            }

    def run(self) -> None:
        try:
            self._set(status="loading_model", error=None)
            model = YOLO(settings.vehicle_model)
            session_id = uuid.uuid4().hex[:10]
            self.session_id = session_id
            source = self._resolve_source(settings.video_source)
            self._set(status="connecting", session_id=session_id)
            capture = cv2.VideoCapture(source)
            if not capture.isOpened():
                raise RuntimeError(f"Could not open video source: {source}")
            fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            counter = LineCounter(int(height * settings.count_line_position), session_id)
            output = self._create_writer(width, height, fps)
            self._set(status="running")
            frame_number = 0
            while not self.stop_event.is_set():
                ok, frame = capture.read()
                if not ok:
                    if settings.video_loop and self._is_local_file(source):
                        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    break
                frame_number += 1
                if settings.inference_stride > 1 and frame_number % settings.inference_stride != 0:
                    if output:
                        output.write(frame)
                    continue
                result = model.track(
                    frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    classes=list(VEHICLE_CLASSES),
                    conf=settings.confidence_threshold,
                    imgsz=settings.inference_width,
                    verbose=False,
                )[0]
                line_y = counter.line_y
                cv2.line(frame, (0, line_y), (width, line_y), (0, 210, 255), 2)
                boxes = result.boxes
                if boxes is not None and boxes.id is not None:
                    coords = boxes.xyxy.cpu().numpy().astype(int)
                    ids = boxes.id.cpu().numpy().astype(int)
                    classes = boxes.cls.cpu().numpy().astype(int)
                    confs = boxes.conf.cpu().numpy()
                    for box, track_id, class_id, confidence in zip(coords, ids, classes, confs):
                        x1, y1, x2, y2 = box.tolist()
                        x1, y1 = max(0, x1), max(0, y1)
                        x2, y2 = min(width, x2), min(height, y2)
                        crop = frame[y1:y2, x1:x2]
                        color = classify_color(crop)
                        crossing = counter.update(int(track_id), (y1 + y2) // 2)
                        label = f"{VEHICLE_CLASSES.get(int(class_id), 'vehicle')} #{track_id} {color}"
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (75, 220, 120), 2)
                        cv2.putText(frame, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (75, 220, 120), 2)
                        if crossing:
                            self.writer.submit(
                                stream_name=settings.stream_name,
                                vehicle_id=crossing.vehicle_id,
                                vehicle_class=VEHICLE_CLASSES.get(int(class_id), "vehicle"),
                                color=color,
                                direction=crossing.direction,
                                confidence=float(confidence),
                            )
                            logger.info("Counted %s (%s) crossing %s", crossing.vehicle_id, color, crossing.direction)
                cv2.putText(frame, f"Total counted: {len(counter.counted)}", (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                if output:
                    output.write(frame)
                with self.state_lock:
                    self.frames_processed += 1
                    self.last_frame_at = time.time()
            capture.release()
            if output:
                output.release()
            self._set(status="stopped")
        except Exception as exc:
            logger.exception("Pipeline failed")
            self._set(status="error", error=str(exc))

    @staticmethod
    def _resolve_source(source: str) -> str | int:
        if source.isdigit():
            return int(source)
        path = Path(source)
        if not path.is_absolute() and "://" not in source:
            local = Path.cwd() / path
            if local.exists():
                return str(local)
        return source

    @staticmethod
    def _is_local_file(source: str | int) -> bool:
        return isinstance(source, str) and "://" not in source

    @staticmethod
    def _create_writer(width: int, height: int, fps: float):
        if not settings.save_annotated_video:
            return None
        path = settings.annotated_video_path
        path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), min(max(fps, 1.0), 60.0), (width, height))
        if not writer.isOpened():
            logger.warning("Could not create annotated output at %s", path)
            return None
        return writer

    def _set(self, **values) -> None:
        with self.state_lock:
            for key, value in values.items():
                setattr(self, key, value)
