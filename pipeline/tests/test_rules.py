"""Tests for the rule layer that turns detections into statuses (zones_analyze.py and analyze.py)."""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import zones_analyze as Z
import analyze as A

FPS = 10
SQUARE = [[100, 100], [300, 100], [300, 300], [100, 300]]

def run_zones(frames, zones):
    d = tempfile.mkdtemp()
    json.dump({'fps': FPS, 'width': 640, 'height': 480, 'model': 'test', 'frames': frames}, open(f'{d}/det.json', 'w'))
    json.dump({'scene': 'Test', 'zones': zones}, open(f'{d}/scene.json', 'w'))
    Z.main(f'{d}/det.json', f'{d}/scene.json', f'{d}/out.json')
    return json.load(open(f'{d}/out.json'))

def person(cx, foot_y, tid=1, conf=0.9): return [0, conf, cx - 20, foot_y - 80, cx + 20, foot_y, tid]

class Geometry(unittest.TestCase):
    def test_point_in_polygon(self):
        self.assertTrue(Z.inside((200, 200), SQUARE)); self.assertFalse(Z.inside((50, 200), SQUARE)); self.assertFalse(Z.inside((200, 350), SQUARE))
    def test_duplicate_boxes_collapse_to_the_confident_one(self):
        objs = [{'kind': 'person', 'conf': .9, 'box': [0, 0, 100, 200]}, {'kind': 'person', 'conf': .5, 'box': [10, 10, 90, 150]}, {'kind': 'pet', 'conf': .6, 'box': [10, 10, 90, 150]}]
        kept = Z.dedupe(objs); self.assertEqual(len(kept), 2); self.assertEqual(kept[0]['conf'], .9)

class EntryRule(unittest.TestCase):
    ZONE = [{'name': 'Door', 'kind': 'entry', 'seconds': 0.3, 'latch': 1.0, 'on_text': 'ENTRY', 'poly': SQUARE}]
    def test_fires_after_threshold_not_on_first_frame(self):
        S = run_zones([[person(200, 200)]] * 10, self.ZONE)
        self.assertEqual(S['frames'][0]['zones'][0]['level'], 'ok')
        self.assertEqual(S['events'][0]['level'], 'alert'); self.assertAlmostEqual(S['events'][0]['t'], 0.3, places=2)
    def test_stays_up_for_latch_then_clears(self):
        S = run_zones([[person(200, 200)]] * 5 + [[]] * 20, self.ZONE)
        levels = [f['zones'][0]['level'] for f in S['frames']]
        self.assertEqual(levels[12], 'alert'); self.assertEqual(levels[-1], 'ok')
    def test_outside_the_zone_never_fires(self):
        S = run_zones([[person(500, 200)]] * 20, self.ZONE); self.assertFalse(S['events'])
    def test_low_confidence_detection_is_ignored(self):
        S = run_zones([[person(200, 200, conf=0.2)]] * 20, self.ZONE); self.assertFalse(S['events'])
    def test_pets_are_logged_without_raising_an_alert(self):
        zone = [{'name': 'Lawn', 'kind': 'entry', 'target': 'pet', 'anchor': 'center', 'seconds': 0.2, 'level': 'info', 'on_text': 'PET', 'poly': SQUARE}]
        S = run_zones([[[16, .8, 180, 180, 220, 220, 3]]] * 10, zone)
        self.assertEqual([e['level'] for e in S['events']], ['info'])
    def test_wrong_kind_does_not_trigger_a_person_zone(self):
        S = run_zones([[[16, .8, 180, 180, 220, 220, 3]]] * 10, self.ZONE); self.assertFalse(S['events'])

class DwellRule(unittest.TestCase):
    ZONE = [{'name': 'Shelf', 'kind': 'dwell', 'seconds': 2, 'poly': SQUARE}]
    def test_alerts_once_someone_has_stayed_long_enough(self):
        S = run_zones([[person(200, 200)]] * 30, self.ZONE)
        self.assertAlmostEqual(S['events'][0]['t'], 2.0, places=1)
        self.assertTrue(S['frames'][-1]['objects'][0]['label'].startswith('DWELL'))
    def test_walking_through_does_not_alert(self):
        S = run_zones([[person(120 + i * 20, 200)] for i in range(9)] + [[person(500, 200)]] * 20, self.ZONE); self.assertFalse(S['events'])
    def test_timer_survives_a_tracker_id_switch(self):
        S = run_zones([[person(200, 200, tid=1)]] * 12 + [[person(202, 200, tid=7)]] * 12, self.ZONE)
        self.assertTrue(S['events']); self.assertLess(S['events'][0]['t'], 2.2)
    def test_timer_restarts_after_a_real_exit(self):
        S = run_zones([[person(200, 200)]] * 12 + [[person(500, 200)]] * 15 + [[person(200, 200)]] * 12, self.ZONE); self.assertFalse(S['events'])

class OccupancyRule(unittest.TestCase):
    ZONE = [{'name': 'Queue', 'kind': 'occupancy', 'limit': 2, 'hold': 0.5, 'poly': SQUARE}]
    three = [person(150, 200, 1), person(200, 250, 2), person(250, 200, 3)]
    def test_needs_sustained_crowding(self):
        S = run_zones([self.three] * 2 + [self.three[:2]] * 10, self.ZONE); self.assertFalse(S['events'])
        S = run_zones([self.three] * 12, self.ZONE); self.assertAlmostEqual(S['events'][0]['t'], 0.5, places=2)
    def test_at_the_limit_is_not_over(self):
        S = run_zones([self.three[:2]] * 20, self.ZONE); self.assertFalse(S['events']); self.assertEqual(S['frames'][-1]['zones'][0]['text'], '2 of 2')

class DeskRules(unittest.TestCase):
    def run_desks(self, frames):
        d = tempfile.mkdtemp(); json.dump({'fps': 24, 'width': 1920, 'height': 1080, 'model': 'test', 'frames': frames}, open(f'{d}/det.json', 'w'))
        A.main(f'{d}/det.json', f'{d}/out.json'); return json.load(open(f'{d}/out.json'))
    seat = [0, .9, 400, 300, 600, 700, 1]
    def test_seat_is_learned_and_goes_absent_when_empty(self):
        S = self.run_desks([[self.seat]] * 48 + [[]] * 48)
        self.assertEqual(len(S['seats']), 1); self.assertEqual([e['to'] for e in S['events']], ['ABSENT'])
        self.assertAlmostEqual(S['events'][0]['t'], 2.0 + A.ABSENT_AFTER, delta=0.1)
    def test_phone_in_hand_counts_but_a_phone_resting_on_the_desk_does_not(self):
        resting = [67, .8, 610, 680, 650, 700, -1]; held = [67, .8, 480, 480, 520, 520, -1]
        S = self.run_desks([[self.seat, resting]] * 72); self.assertFalse(S['events'])
        S = self.run_desks([[self.seat, resting]] * 36 + [[self.seat, held]] * 36); self.assertEqual([e['to'] for e in S['events']], ['PHONE USAGE'])

if __name__ == '__main__': unittest.main()
