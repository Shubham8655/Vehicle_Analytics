"""FastAPI dashboard and read-only analytics endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from .config import settings
from .database import DetectionEvent, SessionLocal, engine, initialize_database
from .persistence import EventWriter
from .pipeline import PipelineRunner

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
writer = EventWriter(settings.event_queue_size)
runner = PipelineRunner(writer)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    writer.start()
    runner.start()
    yield
    runner.stop()
    writer.stop()


app = FastAPI(title="Vehicle Analytics", version="1.0.0", lifespan=lifespan)


def get_analytics() -> tuple[int, int, dict[str, int], list[DetectionEvent]]:
    with SessionLocal() as session:
        total = session.scalar(select(func.count()).select_from(DetectionEvent)) or 0
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today = session.scalar(select(func.count()).select_from(DetectionEvent).where(DetectionEvent.crossed_at >= today_start)) or 0
        rows = session.execute(select(DetectionEvent.color, func.count()).group_by(DetectionEvent.color)).all()
        colors = {color: count for color, count in rows}
        events = list(session.scalars(select(DetectionEvent).order_by(DetectionEvent.crossed_at.desc()).limit(20)))
    return total, today, colors, events


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    total, today, colors, events = get_analytics()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "stats": {"total": total, "today": today, "colors": colors or {"no events": 0}},
            "events": events,
            "pipeline": runner.snapshot(),
            "queue_depth": writer.queue_depth,
            "database_backend": engine.dialect.name,
        },
    )


@app.get("/api/health")
def health():
    snapshot = runner.snapshot()
    return {"status": "ok", "pipeline": snapshot, "database": engine.dialect.name,
            "writer": {"queue_depth": writer.queue_depth, "dropped_events": writer.dropped_events,
                       "persisted_events": writer.persisted_events, "last_error": writer.last_error}}


@app.get("/api/stats")
def stats():
    total, today, colors, _ = get_analytics()
    return {"total": total, "today": today, "colors": colors}


@app.get("/api/events")
def events(limit: int = Query(default=50, ge=1, le=500)):
    with SessionLocal() as session:
        rows = session.scalars(select(DetectionEvent).order_by(DetectionEvent.crossed_at.desc()).limit(limit))
        return [{"id": row.id, "event_id": row.event_id, "stream_name": row.stream_name,
                 "vehicle_id": row.vehicle_id, "vehicle_class": row.vehicle_class, "color": row.color,
                 "direction": row.direction, "confidence": row.confidence,
                 "crossed_at": row.crossed_at.isoformat() if row.crossed_at else None} for row in rows]
