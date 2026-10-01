"""Project-scene coordinates mapped through the observed HCL canvas view.

HCL stores the icon's top-left scene position. The two verified models use a
50-unit icon. Live scrollbar values are required; a saved screenshot position
is not an input to this transform.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


_VERIFIED_ICON_MODELS = {"MSR36-20", "S5820V2-54QS-GE"}


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise ValueError("Coordinates must be finite")


@dataclass(frozen=True)
class CanvasView:
    left: float
    top: float
    width: float
    height: float
    scale_x: float
    scale_y: float
    scroll_x: float
    scroll_y: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (
            self.left, self.top, self.width, self.height, self.scale_x, self.scale_y,
            self.scroll_x, self.scroll_y,
        )):
            raise ValueError("Canvas observations must be finite")
        if min(self.width, self.height, self.scale_x, self.scale_y) <= 0:
            raise ValueError("Canvas dimensions and scales must be positive")

    def device_center(self, model: str, scene_position: Point) -> Point:
        if model not in _VERIFIED_ICON_MODELS:
            raise ValueError(f"Unverified icon geometry for model: {model}")
        return Point(
            self.left + (scene_position.x + 25) * self.scale_x - self.scroll_x,
            self.top + (scene_position.y + 25) * self.scale_y - self.scroll_y,
        )

    def link_point(self, source: Point, target: Point, fraction: float = 0.5) -> Point:
        if not math.isfinite(fraction) or not 0 < fraction < 1:
            raise ValueError("The link fraction must be strictly between its endpoints")
        return Point(source.x + (target.x - source.x) * fraction,
                     source.y + (target.y - source.y) * fraction)

    def require_visible(self, point: Point) -> None:
        if not (self.left < point.x < self.left + self.width and
                self.top < point.y < self.top + self.height):
            raise ValueError("The projected point is outside the observed viewport")
