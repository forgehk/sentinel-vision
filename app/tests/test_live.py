"""Tests for the live app: the tracker, and short end-to-end runs on the sample clips when the models are installed."""
import importlib.util, os, subprocess, sys, unittest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
READY = all(importlib.util.find_spec(m) for m in ('cv2', 'onnxruntime', 'PIL')) and os.path.exists(os.path.join(APP, 'models', 'yolo26n.onnx'))


@unittest.skipUnless(READY, 'needs OpenCV, ONNX Runtime, Pillow and models/yolo26n.onnx')
class TrackerTests(unittest.TestCase):
    def setUp(self):
        import sentinel_live as L
        self.T = L.Tracker()

    def test_a_moving_box_keeps_its_id(self):
        a = self.T.update([(0, [100, 100, 200, 300])], 0.0); b = self.T.update([(0, [110, 104, 210, 304])], 0.1)
        self.assertEqual(a, b)

    def test_a_new_box_gets_a_new_id(self):
        a = self.T.update([(0, [100, 100, 200, 300])], 0.0); b = self.T.update([(0, [104, 100, 204, 300]), (0, [600, 100, 700, 300])], 0.1)
        self.assertEqual(b[0], a[0]); self.assertNotEqual(b[1], a[0])

    def test_two_classes_never_share_a_track(self):
        a = self.T.update([(0, [100, 100, 200, 300])], 0.0); b = self.T.update([(2, [100, 100, 200, 300])], 0.1)
        self.assertNotEqual(a, b)

    def test_a_track_is_dropped_after_it_has_been_gone_a_while(self):
        a = self.T.update([(0, [100, 100, 200, 300])], 0.0); self.T.update([], 2.0); b = self.T.update([(0, [100, 100, 200, 300])], 2.1)
        self.assertNotEqual(a, b)


@unittest.skipUnless(READY, 'needs OpenCV, ONNX Runtime, Pillow and models/yolo26n.onnx')
class EndToEnd(unittest.TestCase):
    def run_app(self, launcher, *args):
        r = subprocess.run([sys.executable, os.path.join(APP, launcher), '--headless', '--model', 'n', '--imgsz', '640', '--device', 'cpu', '--report', *args],
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:]); return r.stdout

    def test_front_yard_sample_reports_the_vehicle_the_pet_and_the_person(self):
        out = self.run_app('SentinelHome.py', '--max-frames', '200')
        for text in ('vehicle arrived', 'pet on lawn, no alert', 'person approaching the door'): self.assertIn(text, out)

    def test_office_sample_maps_seats_and_sees_one_empty(self):
        out = self.run_app('SentinelOffice.py', '--max-frames', '150')
        self.assertRegex(out, r'seats=[456]'); self.assertIn('WORKING -> ABSENT', out)

    def test_a_zone_drawn_with_the_mouse_is_added_and_fires(self):
        clicks = '6:z,7:click@200@150,8:click@1700@150,9:click@1700@1000,10:click@200@1000,11:enter,12:1'
        out = self.run_app('SentinelShop.py', '--max-frames', '60', '--script', '5:c,' + clicks)
        self.assertIn('Zone 1  person entered', out)
        self.assertFalse(os.path.exists(os.path.join(APP, 'zones', 'custom_shop.json')), 'zones drawn on the sample clip must not overwrite your own')

    def test_exam_sample_maps_seats_with_the_pose_model(self):
        out = self.run_app('SentinelExam.py', '--max-frames', '40')
        self.assertRegex(out, r'seats=([5-9]|10)')


if __name__ == '__main__':
    unittest.main()
