"""Exam-hall rules over pose + phone detections. Rules only; nothing is hand-keyed per frame.

    python exam_analyze.py detections.json states.json [scene.json]

  1. Calibration (first CALIB_S seconds): every person who stays put becomes a seat. From their own
     keypoints we take a baseline head direction and a desk zone (an ellipse around where their hands rest).
  2. Per frame, per seat:
       head direction  = nose relative to the midpoint of the ears, in the image plane
       yaw             = how far that direction has rotated from the candidate's own baseline, in degrees
       gaze target     = own paper, another candidate's desk zone (the best-aligned nearby one), or away
       phone           = a phone box inside the candidate's box or desk zone
  3. Risk score, 0 to 100, per seat:
       + LOOK_RATE per second while the head points at someone else's desk (after LOOK_HOLD seconds)
       - DECAY_RATE per second otherwise
       a visible phone lifts the score to at least PHONE_RISK
     NORMAL below REVIEW_AT, REVIEW from there, FLAGGED from FLAG_AT. A flag is a prompt for a person
     to look at the footage. It is not a finding.
"""
import json, math, statistics, sys

NOSE, LEYE, REYE, LEAR, REAR, LSH, RSH, LEL, REL, LWR, RWR = range(11)
CALIB_S = 1.0
PERSON_CONF = 0.40
KP_CONF = 0.35
PHONE_CONF = 0.15
SMOOTH = 0.35            # EMA weight of the newest head direction
YAW_GATE = 38.0        # degrees off baseline before a look leaves own paper
TARGET_TOL = 30.0      # most degrees allowed between head direction and a desk
TARGET_RANGE = 7.0     # a desk must be within this many shoulder-widths
SWITCH_MARGIN = 0.25   # cost gap another desk needs to take over as target
LOOK_HOLD = 0.35       # seconds a look must last before it scores
LOOK_RATE = 42.0       # risk per second while looking at another desk
DECAY_RATE = 7.0       # risk per second while not
PHONE_RISK = 85.0      # a phone at the desk lifts the score to this
PHONE_WINDOW, PHONE_ON, PHONE_OFF = 0.8, 0.35, 1.5
REVIEW_AT, REVIEW_OFF = 25.0, 12.0
FLAG_AT, FLAG_OFF = 60.0, 45.0


def area(b): return max(0, b[2] - b[0]) * max(0, b[3] - b[1])
def inter(a, b): return area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])
def center(b): return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
def wrap(d): return (d + 180.0) % 360.0 - 180.0
def med(v): return statistics.median(v)


def facing(kp, conf=KP_CONF):
    """Head centre, facing vector (nose minus ear midpoint, scaled by head size) and a pitch proxy.
    Returns None when the nose is not visible, for example when the head is seen from behind."""
    n = kp[NOSE]
    if n[2] < conf: return None
    le, re = kp[LEAR], kp[REAR]
    mx, my = (le[0] + re[0]) / 2, (le[1] + re[1]) / 2
    size = max(math.hypot(le[0] - re[0], le[1] - re[1]), 2.0 * math.hypot(kp[LEYE][0] - kp[REYE][0], kp[LEYE][1] - kp[REYE][1]), 8.0)
    fx, fy = (n[0] - mx) / size, (n[1] - my) / size
    ey = (kp[LEYE][1] + kp[REYE][1]) / 2
    return {'c': (mx, my), 'f': (fx, fy), 'size': size, 'pitch': (n[1] - ey) / size}


def direction(f): return math.degrees(math.atan2(f[1], f[0]))


def in_ellipse(p, z, grow=1.0):
    return ((p[0] - z[0]) / (z[2] * grow)) ** 2 + ((p[1] - z[1]) / (z[3] * grow)) ** 2 <= 1.0


def gaze_target(head, f, yaw, seats, own, prev=None):
    """'own', another seat id, or 'away'. A look only leaves the candidate's own paper once the head
    has rotated YAW_GATE degrees from their baseline. Each desk within TARGET_TOL degrees of the head
    direction and within range gets a cost, angular error plus distance, both as a fraction of their limit.
    The lowest cost is the target, so a well-aligned nearby desk beats one that is merely close or merely in line.
    The previous target is kept unless another desk beats it by SWITCH_MARGIN, which stops the label flickering
    between two desks that sit almost in line."""
    if abs(yaw) < YAW_GATE: return 'own'
    d = direction(f); best = None; costs = {}
    for s in seats:
        if s['id'] == own['id']: continue
        vx, vy = s['zone'][0] - head[0], s['zone'][1] - head[1]
        dist = math.hypot(vx, vy)
        if dist > TARGET_RANGE * own['sw']: continue
        err = abs(wrap(math.degrees(math.atan2(vy, vx)) - d))
        cost = err / TARGET_TOL + dist / (TARGET_RANGE * own['sw'])
        if err > TARGET_TOL: continue
        costs[s['id']] = cost
        if best is None or cost < best[0]: best = (cost, s['id'])
    if best is None: return 'away'
    if prev in costs and costs[prev] <= best[0] + SWITCH_MARGIN: return prev
    return best[1]


class RiskMeter:
    """The whole scoring rule for one seat."""
    def __init__(self): self.risk = 0.0; self.status = 'NORMAL'; self.look = 0.0; self.reason = None

    def update(self, dt, target, phone):
        looking = target not in ('own', 'away', None)
        self.look = self.look + dt if looking else 0.0
        if looking and self.look >= LOOK_HOLD: self.risk += LOOK_RATE * dt; self.reason = ('look', target)
        else: self.risk -= DECAY_RATE * dt
        if phone: self.risk = max(self.risk, PHONE_RISK); self.reason = ('phone', None)
        self.risk = min(100.0, max(0.0, self.risk))
        if self.risk >= FLAG_AT: self.status = 'FLAGGED'
        elif self.status == 'FLAGGED' and self.risk >= FLAG_OFF: pass
        elif self.risk >= REVIEW_AT: self.status = 'REVIEW'
        elif self.status in ('REVIEW', 'FLAGGED') and self.risk >= REVIEW_OFF: self.status = 'REVIEW'
        else: self.status = 'NORMAL'
        return self.risk, self.status


def dedupe(people):
    keep = []
    for p in sorted(people, key=lambda p: -p[0]):
        if all(inter(p[1:5], k[1:5]) / (min(area(p[1:5]), area(k[1:5])) + 1e-6) < 0.7 for k in keep): keep.append(p)
    return keep


def calibrate(F, fps, W, H):
    ncal = max(1, int(CALIB_S * fps)); by = {}
    for fr in F[:ncal]:
        for p in dedupe([p for p in fr['people'] if p[0] >= PERSON_CONF and p[5] >= 0]): by.setdefault(p[5], []).append(p)
    seats = []
    for tid, ps in by.items():
        if len(ps) < ncal * 0.6: continue
        box = [med([p[i] for p in ps]) for i in range(1, 5)]
        sws = [math.hypot(p[6][LSH][0] - p[6][RSH][0], p[6][LSH][1] - p[6][RSH][1]) for p in ps if min(p[6][LSH][2], p[6][RSH][2]) >= KP_CONF]
        sw = max(med(sws) if sws else 0.0, 0.42 * (box[2] - box[0]))
        hands = [(k[0], k[1]) for p in ps for k in (p[6][LWR], p[6][RWR]) if k[2] >= KP_CONF]
        cx, cy = (med([h[0] for h in hands]), med([h[1] for h in hands])) if hands else ((box[0] + box[2]) / 2, box[3] - 0.15 * (box[3] - box[1]))
        rx = max(1.05 * sw, 0.52 * (box[2] - box[0])); zone = [cx, cy + 0.10 * rx, rx, 0.50 * rx]
        heads = [h for h in (facing(p[6]) for p in ps) if h]
        base = None
        if len(heads) >= len(ps) * 0.5:
            base = {'dir': direction((med([h['f'][0] for h in heads]), med([h['f'][1] for h in heads]))), 'pitch': med([h['pitch'] for h in heads])}
        seats.append({'box': [round(v, 1) for v in box], 'zone': [round(v, 1) for v in zone], 'sw': round(sw, 1), 'base': base})
    # number seats row by row from the back of the room (top of the image) forward, left to right
    seats.sort(key=lambda s: center(s['box'])[1]); rows = []
    for s in seats:
        cy, h = center(s['box'])[1], s['box'][3] - s['box'][1]
        if rows and cy - rows[-1]['cy'] < 0.45 * h: rows[-1]['m'].append(s)
        else: rows.append({'cy': cy, 'm': [s]})
    seats = [s for r in rows for s in sorted(r['m'], key=lambda s: center(s['box'])[0])]
    for i, s in enumerate(seats): s['id'] = i + 1
    return seats


class ExamRules:
    """Head direction, gaze target, phones and the risk score, one frame at a time.
    The batch script below and the live app both run on this."""
    def __init__(self, seats):
        self.seats = seats; self.events = []
        self.st = {s['id']: {'meter': RiskMeter(), 'f': None, 'phone_hits': [], 'phone_last': -9, 'phone_on': False, 'status': 'NORMAL'} for s in seats}

    def step(self, fr, t, dt):
        """fr: {'people': [...], 'phones': [...]} for one frame at time t (seconds); dt is the time since the previous frame."""
        people = dedupe([p for p in fr['people'] if p[0] >= PERSON_CONF]); phones = [q for q in fr['phones'] if q[0] >= PHONE_CONF]
        taken = set(); rows = []
        for s in self.seats:
            best = None
            for j, p in enumerate(people):
                if j in taken: continue
                o = inter(p[1:5], s['box']) / (area(s['box']) + 1e-6)
                if o >= 0.3 and (best is None or o > best[0]): best = (o, j)
            S = self.st[s['id']]; row = {'id': s['id'], 'person': None, 'head': [], 'hands': [], 'yaw': None, 'pitch': None, 'target': None, 'gaze': None, 'phone': None}
            phone = None
            if best:
                taken.add(best[1]); p = people[best[1]]; kp = p[6]; row['person'] = p[1:5]
                row['head'] = [[k[0], k[1]] for k in kp[:5] if k[2] >= KP_CONF]
                row['hands'] = [[k[0], k[1]] for k in (kp[LWR], kp[RWR]) if k[2] >= KP_CONF]
                h = facing(kp)
                if h and s['base']:
                    S['f'] = h['f'] if S['f'] is None else (SMOOTH * h['f'][0] + (1 - SMOOTH) * S['f'][0], SMOOTH * h['f'][1] + (1 - SMOOTH) * S['f'][1])
                    yaw = wrap(direction(S['f']) - s['base']['dir'])
                    row['yaw'] = round(yaw); row['pitch'] = round(h['pitch'] - s['base']['pitch'], 2)
                    row['target'] = S['target'] = gaze_target(h['c'], S['f'], yaw, self.seats, s, S.get('target'))
                    if row['target'] not in ('own', 'away'):
                        z = next(q['zone'] for q in self.seats if q['id'] == row['target'])
                        row['gaze'] = [round(h['c'][0], 1), round(h['c'][1], 1), z[0], z[1]]
                else: S['f'] = None
                shrunk = p[1:5]
                for q in phones:
                    c = center(q[1:5])
                    if (shrunk[0] <= c[0] <= shrunk[2] and shrunk[1] <= c[1] <= shrunk[3]) or in_ellipse(c, s['zone'], 1.1):
                        if phone is None or q[0] > phone[0]: phone = q
            if phone: S['phone_hits'].append((t, dt)); S['phone_last'] = t; S['phone_box'] = phone[1:5]
            S['phone_hits'] = [x for x in S['phone_hits'] if t - x[0] <= PHONE_WINDOW]
            if not S['phone_on'] and sum(x[1] for x in S['phone_hits']) >= PHONE_ON: S['phone_on'] = True
            if S['phone_on'] and t - S['phone_last'] > PHONE_OFF: S['phone_on'] = False
            if S['phone_on']: row['phone'] = S.get('phone_box')
            risk, status = S['meter'].update(dt, row['target'], S['phone_on'])
            row['risk'] = int(round(risk)); row['status'] = status
            if status != S['status']:
                why = S['meter'].reason
                text = 'phone at the desk' if S['phone_on'] else ('looking at desk S%d' % why[1] if why and why[0] == 'look' and status != 'NORMAL' else 'back on own paper')
                self.events.append({'t': round(t, 2), 'id': s['id'], 'from': S['status'], 'to': status, 'text': text, 'risk': row['risk']})
                S['status'] = status
            rows.append(row)
        extra = [p[1:5] for j, p in enumerate(people) if j not in taken]
        extra = [p[1:5] for j, p in enumerate(people) if j not in taken]
        return {'t': round(t, 3), 'seats': rows, 'unassigned': extra, 'phones': sum(1 for r in rows if r['phone'])}


def main(src, dst, scene=None):
    D = json.load(open(src)); fps = D['fps']; W, H = D['width'], D['height']; F = D['frames']; dt = 1.0 / fps
    cfg = json.load(open(scene)) if scene else {}
    seats = calibrate(F, fps, W, H); R = ExamRules(seats)
    out = [R.step(fr, i / fps, dt) for i, fr in enumerate(F)]; events = R.events
    json.dump({'fps': fps, 'width': W, 'height': H, 'scene': cfg.get('scene', 'Exam hall'), 'panel': cfg.get('panel', 'tl'),
               'tagline': cfg.get('tagline', 'Exam hall  ·  head direction, desk zones, phones'),
               'seats': [{k: s[k] for k in ('id', 'box', 'zone', 'sw', 'base')} for s in seats], 'frames': out, 'events': events}, open(dst, 'w'))
    print(len(seats), 'seats;', len(events), 'status changes')
    for e in events: print('  %5.2fs  S%d  %s -> %s  (%s, risk %d)' % (e['t'], e['id'], e['from'], e['to'], e['text'], e['risk']))


if __name__ == '__main__':
    main(*sys.argv[1:4])
