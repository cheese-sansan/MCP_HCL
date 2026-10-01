from __future__ import annotations

import unittest

from mcp_hcl.geometry import CanvasView, Point


class HclCanvasGeometryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.view = CanvasView(99, 124, 841, 631, 1.1, 1.1, -490, -458)

    def test_verified_device_centers_match_live_observation(self) -> None:
        router = self.view.device_center("MSR36-20", Point(191.36363636363635, -187.72727272727272))
        switch = self.view.device_center("S5820V2-54QS-GE", Point(-127, -323))
        self.assertAlmostEqual(router.x, 827)
        self.assertAlmostEqual(router.y, 403)
        self.assertAlmostEqual(switch.x, 476.8)
        self.assertAlmostEqual(switch.y, 254.2)
        self.view.require_visible(router)

    def test_camera_pan_changes_pixels_without_changing_device_scene_position(self) -> None:
        old_view = CanvasView(99, 124, 841, 631, 1.1, 1.1, -490, -365)
        location = Point(-127, -323)
        before = old_view.device_center("S5820V2-54QS-GE", location)
        after = self.view.device_center("S5820V2-54QS-GE", location)
        self.assertAlmostEqual(after.y - before.y, 93)
        self.assertEqual(before.x, after.x)

    def test_link_projection_and_visibility(self) -> None:
        point = self.view.link_point(Point(827, 403), Point(476.8, 254.2), 0.2)
        self.assertAlmostEqual(point.x, 756.96)
        self.assertAlmostEqual(point.y, 373.24)
        self.view.require_visible(point)
        with self.assertRaises(ValueError):
            self.view.require_visible(Point(0, 0))

    def test_unknown_models_and_invalid_observations_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unverified icon geometry"):
            self.view.device_center("unobserved-model", Point(0, 0))
        with self.assertRaises(ValueError):
            CanvasView(0, 0, 100, 100, 0, 1, 0, 0)
        with self.assertRaises(ValueError):
            Point(float("nan"), 0)


if __name__ == "__main__":
    unittest.main()
