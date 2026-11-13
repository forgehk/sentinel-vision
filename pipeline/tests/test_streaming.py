"""The rule classes take one frame at a time, at whatever rate frames arrive. The live app feeds them this way."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A
import zones_analyze as Z
import exam_analyze as X
from test_exam import person as candidate

SEAT = [0, .9, 400, 300, 600, 700, 1]


class OfficeLive(unittest.TestCase):
    def test_absence_fires_at_the_same_moment_at_any_frame_rate(self):
        for fps in (24, 12, 8):
            R = A.OfficeRules(1920, 1080); R.calibrate([[SEAT]] * fps)
            for i in range(fps * 4): R.step([SEAT] if i / fps < 2.0 else [], i / fps, 1 / fps)
            self.assertEqual([e['to'] for e in R.events], ['ABSENT'], fps)
            self.assertAlmostEqual(R.events[0]['t'], 2.0 + A.ABSENT_AFTER, delta=0.2, msg=fps)

    def test_an_empty_room_calibrates_to_no_seats(self):
        R = A.OfficeRules(1920, 1080); self.assertEqual(R.calibrate([[]] * 24), [])
        self.assertEqual(R.step([], 1.0, 1 / 24)['desks'], [])

    def test_recalibrating_starts_a_clean_event_list(self):
        R = A.OfficeRules(1920, 1080); R.calibrate([[SEAT]] * 24)
        for i in range(48): R.step([], i / 24, 1 / 24)
        self.assertTrue(R.events); R.calibrate([[SEAT]] * 24); self.assertEqual(R.events, [])


class ZonesLive(unittest.TestCase):
    def zone(self): return [{'name': 'Door', 'kind': 'entry', 'seconds': 0.35, 'latch': 1.0, 'anchor': 'center', 'poly': [[100, 100], [300, 100], [300, 300], [100, 300]]}]

    def test_entry_fires_on_uneven_frame_times(self):
        R = Z.ZoneRules(self.zone()); inside = [0, .9, 180, 160, 220, 240, 7]
        for t in (0.0, 0.05, 0.21, 0.30, 0.44, 0.52): R.step([inside], t)
        self.assertEqual([(e['zone'], e['level']) for e in R.events], [('Door', 'alert')]); self.assertAlmostEqual(R.events[0]['t'], 0.44, places=2)

    def test_a_frame_with_no_detections_is_fine(self):
        R = Z.ZoneRules(self.zone()); fr = R.step([], 0.0)
        self.assertEqual(fr['objects'], []); self.assertEqual(fr['zones'][0]['level'], 'ok')


class ExamLive(unittest.TestCase):
    def rules(self, fps):
        seats = X.calibrate([{'people': [candidate(300, 300, 90, 1), candidate(520, 300, 90, 2)], 'phones': []}] * fps, fps, 1920, 1080)
        return X.ExamRules(seats)

    def test_a_phone_flags_at_the_same_moment_at_any_frame_rate(self):
        for fps in (24, 12, 8):
            R = self.rules(fps)
            for i in range(fps * 4):
                t = i / fps
                R.step({'people': [candidate(300, 300, 90, 1), candidate(520, 300, 90, 2)], 'phones': [[0.6, 505, 380, 535, 400]] if t >= 2.0 else []}, t, 1 / fps)
            self.assertEqual([(e['id'], e['to']) for e in R.events], [(2, 'FLAGGED')], fps)
            self.assertAlmostEqual(R.events[0]['t'], 2.0 + X.PHONE_ON, delta=0.15, msg=fps)

    def test_one_candidate_alone_can_look_away_without_scoring(self):
        seats = X.calibrate([{'people': [candidate(300, 300, 90, 1)], 'phones': []}] * 24, 24, 1920, 1080); R = X.ExamRules(seats)
        for i in range(72): row = R.step({'people': [candidate(300, 300, 10, 1)], 'phones': []}, i / 24, 1 / 24)
        self.assertEqual(row['seats'][0]['target'], 'away'); self.assertEqual(row['seats'][0]['risk'], 0); self.assertEqual(R.events, [])


if __name__ == '__main__':
    unittest.main()
