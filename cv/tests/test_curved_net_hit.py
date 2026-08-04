import importlib.util
import unittest


HAS_OPENCV = importlib.util.find_spec("cv2") is not None

if HAS_OPENCV:
    from cv.events.net_hit.curved_detector import CurvedNetHitConfig, detect_curved_net_hits, event_to_json
    from cv.events.net_hit.curved_geometry import NetBandModel


@unittest.skipUnless(HAS_OPENCV, "OpenCV is required by curved net geometry")
class CurvedNetHitContractTest(unittest.TestCase):
    def test_detects_reversal_inside_curved_net_band_with_legacy_distance_field(self) -> None:
        net_model = NetBandModel(
            lower_line=((0.0, 120.0), (200.0, 120.0)),
            top_coefficients=[100.0],
            x_center=100.0,
            x_scale=100.0,
            top_points=[],
            source="test",
            frame_size={"width": 200, "height": 160},
            expected_height_px=20.0,
            search_height_px=24.0,
            band_margin_px=8.0,
        )
        track = [(100.0, y) for y in (70.0, 80.0, 90.0, 100.0, 110.0, 104.0, 96.0, 88.0)]

        events = detect_curved_net_hits(track, net_model, CurvedNetHitConfig(fps=30.0))

        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0].signed_distance_px, float)
        payload = event_to_json(events[0])
        self.assertIn("signed_distance_px", payload)
        self.assertIn("distance_to_band_px", payload)


if __name__ == "__main__":
    unittest.main()
