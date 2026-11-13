"""Turn raw detections into per-desk status over time. Rules only; nothing is hand-keyed per frame.

  1. Calibration (first CALIB_S seconds): every person who stays put becomes a seat. The seat zone is
     that person's median box, padded. Phones seen lying still in that window are "resting spots".
  2. Per frame, each seat takes the person box that overlaps its zone most.
       no person for ABSENT_AFTER s                      -> ABSENT
       phone box inside the person's box, not at a
       resting spot, for PHONE_ON s within a short window -> PHONE USAGE
       otherwise                                          -> WORKING  (= at desk, no phone in hand)
  3. People not matched to a seat are reported as unassigned (someone walking through).
"""
import json, statistics, sys

CALIB_S = 1.0
PERSON_CONF = 0.35
PHONE_CONF = 0.12
ZONE_PAD = 0.14          # seat zone = median person box grown by this fraction
ABSENT_AFTER = 0.75      # seconds with nobody in the seat
RETURN_AFTER = 0.4
PHONE_WINDOW = 0.8       # look-back window for phone evidence
PHONE_ON = 0.35          # evidence needed inside the window to switch on
PHONE_OFF = 1.5          # seconds without evidence to switch off
SHRINK = 0.10            # phone must sit inside the person box shrunk by this much per side

def area(b): return max(0, b[2] - b[0]) * max(0, b[3] - b[1])
def inter(a, b): return area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])
def center(b): return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)

def dedupe(boxes, conf_index=4):
    """Drop a person box that is mostly contained in (or mostly contains) a more confident one."""
    keep = []
    for b in sorted(boxes, key=lambda b: -b[conf_index]):
        if all(inter(b, k) / (min(area(b), area(k)) + 1e-6) < 0.7 for k in keep): keep.append(b)
    return keep

class OfficeRules:
    """Seats and desk statuses, one frame at a time. The batch script below and the live app both run on this."""
    def __init__(self, W, H):
        self.W, self.H = W, H; self.seats = []; self.resting = []; self.st = {}; self.events = []

    def calibrate(self, frames):
        """frames: the detections seen during the calibration window (the first CALIB_S seconds)."""
        W, H = self.W, self.H; ncal = max(1, len(frames))
        by_track = {}
        for f in frames:
            for x1, y1, x2, y2, conf, tid in dedupe([[x1, y1, x2, y2, conf, tid] for c, conf, x1, y1, x2, y2, tid in f if c == 0 and conf >= PERSON_CONF and tid >= 0]):
                by_track.setdefault(tid, []).append([x1, y1, x2, y2])
        seats = []
        for tid, boxes in by_track.items():
            if len(boxes) < ncal * 0.6: continue
            med = [statistics.median(b[i] for b in boxes) for i in range(4)]
            w, h = med[2] - med[0], med[3] - med[1]
            zone = [max(0, med[0] - w * ZONE_PAD), max(0, med[1] - h * ZONE_PAD), min(W, med[2] + w * ZONE_PAD), min(H, med[3] + h * ZONE_PAD)]
            seats.append({'zone': [round(v, 1) for v in zone], 'seed': med})
        if seats:
            # number seats back-to-front, left-to-right: split into a left and right column of desks, rank by depth
            mid = statistics.median(center(s['seed'])[0] for s in seats)
            for col in (0, 1):
                members = sorted((s for s in seats if (center(s['seed'])[0] > mid) == bool(col)), key=lambda s: center(s['seed'])[1])
                for rank, s in enumerate(members): s['order'] = (rank, col)
            seats.sort(key=lambda s: s['order'])
        for i, s in enumerate(seats): s['id'] = i + 1
        resting = []
        for f in frames:
            for c, conf, x1, y1, x2, y2, tid in f:
                if c == 67 and conf >= PHONE_CONF:
                    cx, cy = center([x1, y1, x2, y2]); size = max(x2 - x1, y2 - y1)
                    if not any(abs(cx - r[0]) < r[2] and abs(cy - r[1]) < r[2] for r in resting): resting.append((cx, cy, size * 1.5))
        self.seats = seats; self.resting = resting; self.events = []
        self.st = {s['id']: {'status': 'WORKING', 'gone': 0.0, 'back': 0.0, 'phone_hist': [], 'phone_last': -1e9} for s in seats}
        return seats

    def step(self, f, t, dt):
        """One frame of detections at time t (seconds); dt is the time since the previous frame."""
        seats, st, resting = self.seats, self.st, self.resting
        people = dedupe([[x1, y1, x2, y2, conf] for c, conf, x1, y1, x2, y2, tid in f if c == 0 and conf >= PERSON_CONF])
        phones = [[x1, y1, x2, y2, conf] for c, conf, x1, y1, x2, y2, tid in f if c == 67 and conf >= PHONE_CONF]
        # greedy seat <- person by share of the person box that lies in the seat zone
        cand = sorted(((inter(p, s['zone']) / (area(p) + 1e-6), si, pi) for si, s in enumerate(seats) for pi, p in enumerate(people)), reverse=True)
        seat_p, used = {}, set()
        for score, si, pi in cand:
            if score < 0.55 or si in seat_p or pi in used: continue
            seat_p[si] = pi; used.add(pi)
        row = {'t': round(t, 3), 'desks': [], 'unassigned': [[round(v) for v in p[:4]] for pi, p in enumerate(people) if pi not in used]}
        for si, s in enumerate(seats):
            S = st[s['id']]; prev = S['status']; p = people[seat_p[si]] if si in seat_p else None
            phone = None
            if p is not None:
                w, h = p[2] - p[0], p[3] - p[1]
                core = [p[0] + w * SHRINK, p[1] + h * SHRINK, p[2] - w * SHRINK, p[3] - h * SHRINK]
                for q in phones:
                    cx, cy = center(q)
                    if core[0] <= cx <= core[2] and core[1] <= cy <= core[3] and not any(abs(cx - r[0]) < r[2] and abs(cy - r[1]) < r[2] for r in resting):
                        if phone is None or q[4] > phone[4]: phone = q
            S['phone_hist'].append((t, phone is not None, dt))
            S['phone_hist'] = [x for x in S['phone_hist'] if t - x[0] <= PHONE_WINDOW]
            if phone is not None: S['phone_last'] = t
            evidence = sum(x[2] for x in S['phone_hist'] if x[1])
            if p is None: S['gone'] += dt; S['back'] = 0.0
            else: S['back'] += dt; S['gone'] = 0.0
            if prev == 'ABSENT':
                status = 'WORKING' if S['back'] >= RETURN_AFTER else 'ABSENT'
            elif S['gone'] >= ABSENT_AFTER: status = 'ABSENT'
            elif prev == 'PHONE USAGE': status = 'PHONE USAGE' if t - S['phone_last'] < PHONE_OFF else 'WORKING'
            elif evidence >= PHONE_ON: status = 'PHONE USAGE'
            else: status = 'WORKING'
            if status != prev: self.events.append({'t': round(t, 2), 'id': s['id'], 'from': prev, 'to': status})
            S['status'] = status
            row['desks'].append({'id': s['id'], 'status': status, 'person': [round(v) for v in p[:4]] if p is not None else None,
                                 'conf': round(p[4], 2) if p is not None else None,
                                 'phone': [round(v) for v in phone[:4]] if phone is not None else None})
        return row


def main(src, dst):
    D = json.load(open(src)); fps = D['fps']; W, H = D['width'], D['height']; F = D['frames']
    R = OfficeRules(W, H); seats = R.calibrate(F[:max(1, int(CALIB_S * fps))])
    out = [R.step(f, fi / fps, 1 / fps) for fi, f in enumerate(F)]
    json.dump({'fps': fps, 'width': W, 'height': H, 'model': D['model'], 'seats': [{'id': s['id'], 'zone': s['zone']} for s in seats],
               'resting_phones': [[round(v) for v in r] for r in R.resting], 'frames': out, 'events': R.events}, open(dst, 'w'))
    print('seats:', [(s['id'], [round(v) for v in s['zone']]) for s in seats]); print('resting phones:', [[round(v) for v in r] for r in R.resting])
    for e in R.events: print(e)

if __name__ == '__main__': main(sys.argv[1], sys.argv[2])
