"""SQLAlchemy database setup and portable schema."""

from __future__ import annotations

from sqlalchemy import DateTime, Float, Integer, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


class DetectionEvent(Base):
    """A single tracked vehicle crossing the configured counting line."""

    __tablename__ = "detection_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    stream_name: Mapped[str] = mapped_column(String(120), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(120), index=True)
    vehicle_class: Mapped[str] = mapped_column(String(40))
    color: Mapped[str] = mapped_column(String(24), index=True)
    direction: Mapped[str] = mapped_column(String(16), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    crossed_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


def make_engine(url: str | None = None):
    db_url = url or settings.database_url
    kwargs = {"pool_pre_ping": True}
    if db_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(db_url, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def initialize_database(target_engine=None) -> None:
    Base.metadata.create_all(target_engine or engine)
