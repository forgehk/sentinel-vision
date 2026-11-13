import json, math, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import exam_analyze as X


def kp(cx, cy, angle_deg, nose_conf=0.95):
    """A seated person's 17 keypoints with the head facing `angle_deg` in the image plane (90 = down the frame)."""
    a = math.radians(angle_deg); k = [[0.0, 0.0, 0.0] for _ in range(17)]
    k[X.NOSE] = [cx + 12 * math.cos(a), cy + 12 * math.sin(a), nose_conf]
    k[X.LEYE], k[X.REYE] = [cx + 5, cy + 2, 0.9], [cx - 5, cy + 2, 0.9]
    k[X.LEAR], k[X.REAR] = [cx + 10, cy, 0.9], [cx - 10, cy, 0.9]
    k[X.LSH], k[X.RSH] = [cx + 30, cy + 40, 0.9], [cx - 30, cy + 40, 0.9]
    k[X.LWR], k[X.RWR] = [cx + 20, cy + 90, 0.9], [cx - 20, cy + 90, 0.9]
    return k


def person(cx, cy, angle, tid, **kw): return [0.9, cx - 50, cy - 30, cx + 50, cy + 120, tid, kp(cx, cy, angle, **kw)]


def clip(turn_from=None, turn_to=None, phone_from=None, seconds=6.0, fps=24.0):
    """Two candidates side by side. Seat 1 (left) can turn toward seat 2's desk; seat 2 can show a phone."""
    frames = []
    for i in range(int(seconds * fps)):
        t = i / fps
        turned = turn_from is not None and turn_from <= t < turn_to
        people = [person(300, 300, 22 if turned else 90, 1), person(520, 300, 90, 2)]
        phones = [[0.6, 505, 380, 535, 400]] if phone_from is not None and t >= phone_from else []
        frames.append({'people': people, 'phones': phones})
    return {'fps': fps, 'width': 1920, 'height': 1080, 'frames': frames}


def run(data):
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, 'in.json'), os.path.join(d, 'out.json')
        json.dump(data, open(src, 'w')); X.main(src, dst); return json.load(open(dst))


class Head(unittest.TestCase):
    def test_no_direction_without_a_visible_nose(self):
        self.assertIsNone(X.facing(kp(100, 100, 90, nose_conf=0.1)))

    def test_direction_follows_the_nose(self):
        for angle in (0, 45, 90, 135, 180):
            self.assertAlmostEqual(X.wrap(X.direction(X.facing(kp(100, 100, angle))['f']) - angle), 0, delta=0.5)

    def test_wrap_keeps_angles_within_half_a_turn(self):
        self.assertEqual(X.wrap(190), -170); self.assertEqual(X.wrap(-190), 170); self.assertEqual(X.wrap(45), 45)


class Gaze(unittest.TestCase):
    def setUp(self):
        self.own = {'id': 1, 'zone': [300, 400, 60, 30], 'sw': 60}
        self.seats = [self.own, {'id': 2, 'zone': [520, 400, 60, 30], 'sw': 60}, {'id': 3, 'zone': [1500, 400, 60, 30], 'sw': 60}]

    def aim(self, deg): a = math.radians(deg); return (math.cos(a), math.sin(a))

    def test_small_head_turns_stay_on_own_paper(self):
        self.assertEqual(X.gaze_target((300, 300), self.aim(60), X.YAW_GATE - 1, self.seats, self.own), 'own')

    def test_head_pointing_at_the_next_desk(self):
        self.assertEqual(X.gaze_target((300, 300), self.aim(24), -66, self.seats, self.own), 2)

    def test_the_closer_of_two_desks_in_line_is_the_target(self):
        behind = {'id': 4, 'zone': [700, 395, 60, 30], 'sw': 60}
        self.assertEqual(X.gaze_target((300, 300), self.aim(15), -75, [self.own, behind, self.seats[1]], self.own), 2)

    def test_a_well_aligned_desk_beats_a_slightly_closer_one_off_to_the_side(self):
        aligned = {'id': 5, 'zone': [540, 425, 60, 30], 'sw': 60}      # dead ahead of the head direction
        closer = {'id': 6, 'zone': [540, 300, 60, 30], 'sw': 60}       # a little nearer, 27 degrees off it
        self.assertEqual(X.gaze_target((300, 300), self.aim(27.5), -62, [self.own, closer, aligned], self.own), 5)

    def test_the_current_target_is_kept_until_another_desk_is_clearly_better(self):
        a = {'id': 5, 'zone': [540, 425, 60, 30], 'sw': 60}; b = {'id': 6, 'zone': [560, 330, 60, 30], 'sw': 60}
        seats = [self.own, a, b]
        self.assertEqual(X.gaze_target((300, 300), self.aim(14), -76, seats, self.own), 6)                # b is the better fit on its own
        self.assertEqual(X.gaze_target((300, 300), self.aim(14), -76, seats, self.own, prev=5), 5)        # but not by enough to take over from a
        self.assertEqual(X.gaze_target((300, 300), self.aim(2), -88, seats, self.own, prev=5), 6)         # once a is well off the head direction, b takes over

    def test_turned_but_pointing_at_no_desk_is_away(self):
        self.assertEqual(X.gaze_target((300, 300), self.aim(-90), 180, self.seats, self.own), 'away')

    def test_far_desks_are_out_of_range(self):
        self.assertEqual(X.gaze_target((300, 300), self.aim(5), -85, [self.own, self.seats[2]], self.own), 'away')


class Risk(unittest.TestCase):
    def test_a_glance_shorter_than_the_hold_scores_nothing(self):
        m = X.RiskMeter()
        for _ in range(int(X.LOOK_HOLD * 24) - 1): m.update(1 / 24, 2, False)
        self.assertEqual(m.risk, 0); self.assertEqual(m.status, 'NORMAL')

    def test_a_sustained_look_goes_to_review_then_flagged(self):
        m = X.RiskMeter(); seen = []
        for _ in range(int(2.2 * 24)):
            m.update(1 / 24, 2, False)
            if not seen or seen[-1] != m.status: seen.append(m.status)
        self.assertEqual(seen, ['NORMAL', 'REVIEW', 'FLAGGED'])

    def test_score_decays_once_the_candidate_is_back_on_their_paper(self):
        m = X.RiskMeter()
        for _ in range(int(2.2 * 24)): m.update(1 / 24, 2, False)
        for _ in range(int(12 * 24)): m.update(1 / 24, 'own', False)
        self.assertEqual(m.status, 'NORMAL'); self.assertLess(m.risk, X.REVIEW_OFF)

    def test_a_phone_flags_immediately(self):
        m = X.RiskMeter(); m.update(1 / 24, 'own', True)
        self.assertEqual(m.status, 'FLAGGED'); self.assertGreaterEqual(m.risk, X.PHONE_RISK)

    def test_looking_away_from_every_desk_is_not_scored(self):
        m = X.RiskMeter()
        for _ in range(48): m.update(1 / 24, 'away', False)
        self.assertEqual(m.risk, 0)


class EndToEnd(unittest.TestCase):
    def test_seats_are_calibrated_and_numbered_left_to_right(self):
        S = run(clip())
        self.assertEqual([s['id'] for s in S['seats']], [1, 2]); self.assertLess(S['seats'][0]['box'][0], S['seats'][1]['box'][0])
        self.assertEqual(S['events'], [])

    def test_looking_at_the_neighbouring_desk_is_flagged_with_its_seat(self):
        S = run(clip(turn_from=1.5, turn_to=4.0))
        flagged = [e for e in S['events'] if e['to'] == 'FLAGGED']
        self.assertEqual(len(flagged), 1); self.assertEqual(flagged[0]['id'], 1); self.assertEqual(flagged[0]['text'], 'looking at desk S2')
        row = next(r for r in S['frames'][int(3.0 * 24)]['seats'] if r['id'] == 1)
        self.assertEqual(row['target'], 2); self.assertAlmostEqual(row['yaw'], -68, delta=3); self.assertIsNotNone(row['gaze'])
        self.assertTrue(all(r['status'] == 'NORMAL' for f in S['frames'] for r in f['seats'] if r['id'] == 2))

    def test_a_phone_at_a_desk_flags_that_seat_only(self):
        S = run(clip(phone_from=2.0))
        self.assertEqual([(e['id'], e['to'], e['text']) for e in S['events']], [(2, 'FLAGGED', 'phone at the desk')])
        self.assertAlmostEqual(S['events'][0]['t'], 2.0 + X.PHONE_ON, delta=0.1)


if __name__ == '__main__':
    unittest.main()
