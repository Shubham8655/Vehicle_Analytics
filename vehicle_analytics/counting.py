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
        self.sides: dict[int, int] = {}
        self.counted: set[int] = set()

    def update(self, track_id: int, center_y: int) -> Crossing | None:
        if track_id in self.counted:
            return None
        current_side = -1 if center_y < self.line_y - self.deadband else 1 if center_y > self.line_y + self.deadband else 0
        previous_side = self.sides.get(track_id)
        if current_side == 0:
            return None
        self.sides[track_id] = current_side
        if previous_side is None or previous_side == current_side:
            return None
        self.counted.add(track_id)
        direction = "down" if previous_side < current_side else "up"
        return Crossing(vehicle_id=f"{self.session_id}:{track_id}", direction=direction)
