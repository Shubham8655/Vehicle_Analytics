"""Track-aware line crossing state; each track can emit at most one event."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Crossing:
    vehicle_id: str
    direction: str


class LineCounter:
    def __init__(self, line_y: int, session_id: str, deadband: int = 6):
        self.line_y = line_y
        self.session_id = session_id
        self.deadband = deadband
        self.previous_y: dict[int, int] = {}
        self.counted: set[int] = set()

    def update(self, track_id: int, center_y: int) -> Crossing | None:
        previous = self.previous_y.get(track_id)
        self.previous_y[track_id] = center_y
        if track_id in self.counted or previous is None:
            return None
        direction = None
        if previous < self.line_y - self.deadband and center_y >= self.line_y + self.deadband:
            direction = "down"
        elif previous > self.line_y + self.deadband and center_y <= self.line_y - self.deadband:
            direction = "up"
        if direction is None:
            return None
        self.counted.add(track_id)
        return Crossing(vehicle_id=f"{self.session_id}:{track_id}", direction=direction)
