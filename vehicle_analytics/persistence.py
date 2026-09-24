"""Bounded queue and background database writer for inference events."""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from collections.abc import Callable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import DetectionEvent, SessionLocal

logger = logging.getLogger(__name__)


class EventWriter:
    def __init__(self, max_queue_size: int = 2000, session_factory: Callable[[], Session] = SessionLocal):
        self.queue: queue.Queue[dict | None] = queue.Queue(maxsize=max_queue_size)
        self.session_factory = session_factory
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.dropped_events = 0
        self.persisted_events = 0
        self.last_error: str | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="event-writer", daemon=True)
        self.thread.start()

    def submit(self, *, stream_name: str, vehicle_id: str, vehicle_class: str, color: str,
               direction: str, confidence: float) -> bool:
        payload = {
            "event_id": str(uuid.uuid4()),
            "stream_name": stream_name,
            "vehicle_id": vehicle_id,
            "vehicle_class": vehicle_class,
            "color": color,
            "direction": direction,
            "confidence": float(confidence),
            "crossed_at": datetime.now(timezone.utc),
        }
        try:
            self.queue.put_nowait(payload)
            return True
        except queue.Full:
            self.dropped_events += 1
            logger.error("Detection event queue is full; event dropped (%s)", vehicle_id)
            return False

    def _run(self) -> None:
        while not self.stop_event.is_set() or not self.queue.empty():
            try:
                item = self.queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if item is None:
                self.queue.task_done()
                continue
            try:
                with self.session_factory() as session:
                    session.add(DetectionEvent(**item))
                    session.commit()
                self.persisted_events += 1
                self.last_error = None
            except SQLAlchemyError as exc:
                self.last_error = str(exc)
                logger.exception("Could not persist detection event")
                time.sleep(0.5)
            finally:
                self.queue.task_done()

    def stop(self, timeout: float = 5.0) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=timeout)

    @property
    def queue_depth(self) -> int:
        return self.queue.qsize()
