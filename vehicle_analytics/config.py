"""Environment-backed application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _as_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{(PROJECT_ROOT / 'vehicle_analytics.db').as_posix()}")
    video_source: str = os.getenv("VIDEO_SOURCE", str(PROJECT_ROOT / "traffic.mp4"))
    video_loop: bool = _as_bool("VIDEO_LOOP", True)
    stream_name: str = os.getenv("STREAM_NAME", "traffic-camera-01")
    vehicle_model: str = os.getenv("VEHICLE_MODEL", "yolo11n.pt")
    confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.35"))
    inference_width: int = int(os.getenv("INFERENCE_WIDTH", "640"))
    inference_stride: int = int(os.getenv("INFERENCE_STRIDE", "1"))
    count_line_position: float = float(os.getenv("COUNT_LINE_POSITION", "0.55"))
    save_annotated_video: bool = _as_bool("SAVE_ANNOTATED_VIDEO", True)
    annotated_video_path: Path = Path(os.getenv("ANNOTATED_VIDEO_PATH", str(PROJECT_ROOT / "runs" / "annotated.mp4")))
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    event_queue_size: int = int(os.getenv("EVENT_QUEUE_SIZE", "2000"))


settings = Settings()
