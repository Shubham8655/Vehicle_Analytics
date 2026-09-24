from __future__ import annotations

import unittest

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from vehicle_analytics.colors import classify_color
from vehicle_analytics.counting import LineCounter
from vehicle_analytics.database import Base, DetectionEvent
from vehicle_analytics.persistence import EventWriter
from vehicle_analytics.web import app


class LineCounterTests(unittest.TestCase):
    def test_counts_crossing_once_and_names_direction(self):
        counter = LineCounter(line_y=100, session_id="abc", deadband=4)
        self.assertIsNone(counter.update(3, 80))
        event = counter.update(3, 120)
        self.assertEqual((event.vehicle_id, event.direction), ("abc:3", "down"))
        self.assertIsNone(counter.update(3, 80))

    def test_ignores_motion_within_line_deadband(self):
        counter = LineCounter(line_y=100, session_id="abc", deadband=5)
        counter.update(1, 98)
        self.assertIsNone(counter.update(1, 103))

    def test_counts_gradual_crossing_through_deadband(self):
        counter = LineCounter(line_y=100, session_id="abc", deadband=5)
        counter.update(9, 80)
        counter.update(9, 95)
        counter.update(9, 100)
        event = counter.update(9, 108)
        self.assertEqual(event.direction, "down")

    def test_counts_upward_crossing(self):
        counter = LineCounter(line_y=100, session_id="abc", deadband=3)
        counter.update(5, 120)
        self.assertEqual(counter.update(5, 80).direction, "up")


class ColorTests(unittest.TestCase):
    def test_classifies_solid_color_crop(self):
        colors = {"red": (0, 0, 255), "blue": (255, 0, 0), "green": (0, 255, 0)}
        for label, bgr in colors.items():
            with self.subTest(label=label):
                crop = np.full((80, 120, 3), bgr, dtype=np.uint8)
                self.assertEqual(classify_color(crop), label)

    def test_classifies_neutral_crop(self):
        crop = np.full((60, 80, 3), (200, 200, 200), dtype=np.uint8)
        self.assertEqual(classify_color(crop), "white")


class PersistenceSchemaTests(unittest.TestCase):
    def test_schema_creates_on_sqlite(self):
        test_engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(test_engine)
        self.assertIn("detection_events", Base.metadata.tables)
        self.assertTrue(DetectionEvent.__table__.c.event_id.unique)

    def test_background_writer_persists_event(self):
        test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(test_engine)
        test_sessions = sessionmaker(bind=test_engine, expire_on_commit=False)
        writer = EventWriter(max_queue_size=2, session_factory=test_sessions)
        writer.start()
        self.assertTrue(writer.submit(stream_name="camera", vehicle_id="session:1", vehicle_class="car",
                                      color="blue", direction="down", confidence=0.9))
        writer.queue.join()
        writer.stop()
        with test_sessions() as session:
            row = session.scalar(select(DetectionEvent))
            self.assertEqual((row.vehicle_id, row.color, row.direction), ("session:1", "blue", "down"))
        test_engine.dispose()


class WebSmokeTests(unittest.TestCase):
    def test_health_and_api_shapes(self):
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/health").status_code, 200)
            stats = client.get("/api/stats").json()
            self.assertIsInstance(stats["total"], int)
            self.assertIsInstance(stats["colors"], dict)
            self.assertIsInstance(client.get("/api/events?limit=10").json(), list)
            self.assertIn("Vehicle analytics", client.get("/").text)


if __name__ == "__main__":
    unittest.main()
