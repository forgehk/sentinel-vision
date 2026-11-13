"""Turn raw detections into per-zone status over time, for scenes described by drawn zones.

    python zones_analyze.py detections.json scene.json states.json

scene.json lists the zones (polygons in source pixels) and one rule each:
  dwell      someone stays in the zone longer than `seconds`
  entry      something of the target kind is in the zone for `seconds` (alert, notice or just logged)
  occupancy  more than `limit` of the target kind are in the zone for `hold` seconds
Nothing is keyed by hand per frame: statuses come from the detections and these rules.
"""
import json, sys

KIND = {0: 'person', 1: 'vehicle', 2: 'vehicle', 3: 'vehicle', 5: 'vehicle', 7: 'vehicle', 15: 'pet', 16: 'pet'}
MIN_CONF = {'person': 0.35, 'vehicle': 0.35, 'pet': 0.25}
EXIT_GRACE = 0.6      # seconds a track may vanish or step out before its timer resets
INHERIT_S, INHERIT_PX = 1.0, 90   # a new track this close to a just-lost one keeps its timer (tracker ID switches)

def area(b): return max(0, b[2] - b[0]) * max(0, b[3] - b[1])
def inter(a, b): return area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])

def dedupe(objs):
    keep = []
    for o in sorted(objs, key=lambda o: -o['conf']):
        if all(o['kind'] != k['kind'] or inter(o['box'], k['box']) / (min(area(o['box']), area(k['box'])) + 1e-6) < 0.7 for k in keep): keep.append(o)
    return keep

def inside(pt, poly):
    x, y = pt; hit = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1: hit = not hit
    return hit

def anchor(box, how):
    return ((box[0] + box[2]) / 2, box[3]) if how == 'foot' else ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)

class ZoneRules:
    """Zone statuses, one frame at a time. The batch script below and the live app both run on this."""
    def __init__(self, zones):
        self.zones = zones; self.events = []
        for z in zones:
            z.setdefault('target', 'person'); z.setdefault('anchor', 'foot'); z.setdefault('level', 'alert'); z.setdefault('latch', 2.5); z.setdefault('on_text', 'ENTRY')
            z['_tracks'] = {}; z['_since'] = None; z['_last'] = -1e9; z['_over'] = None; z['_prev'] = 'ok'; z['_fired'] = -1e9

    def step(self, raw, t):
        """raw: one frame of detections as [class, conf, x1, y1, x2, y2, track_id] rows; t in seconds."""
        objs = dedupe([{'id': tid, 'kind': KIND[c], 'conf': conf, 'box': [x1, y1, x2, y2]} for c, conf, x1, y1, x2, y2, tid in raw
                       if c in KIND and conf >= MIN_CONF[KIND[c]]])
        for o in objs: o['level'] = 'ok'; o['label'] = o['kind'].upper()
        zrows = []
        for z in self.zones:
            members = [o for o in objs if o['kind'] == z['target'] and inside(anchor(o['box'], z['anchor']), z['poly'])]
            level, text = 'ok', z.get('clear_text', 'CLEAR')
            if z['kind'] == 'dwell':
                T = z['_tracks']
                for o in members:
                    key = o['id'] if o['id'] >= 0 else ('anon', round(o['box'][0] / 40), round(o['box'][1] / 40))
                    a = anchor(o['box'], z['anchor'])
                    if key not in T:
                        heir = [k for k, v in T.items() if t - v['last'] <= INHERIT_S and t - v['last'] > 0 and abs(v['pt'][0] - a[0]) < INHERIT_PX and abs(v['pt'][1] - a[1]) < INHERIT_PX]
                        T[key] = {'since': T.pop(heir[0])['since'] if heir else t, 'last': t, 'pt': a}
                    T[key]['last'] = t; T[key]['pt'] = a
                    dwell = t - T[key]['since']
                    if dwell >= z['seconds']: o['level'] = 'alert'; o['label'] = f'DWELL {dwell:.1f}s'
                for k in [k for k, v in T.items() if t - v['last'] > INHERIT_S]: del T[k]
                live = [t - v['since'] for v in T.values() if t - v['last'] <= EXIT_GRACE]
                longest = max(live, default=0)
                if longest >= z['seconds']: level, text = 'alert', f'DWELL {longest:.1f}s'
                elif live: text = f'{longest:.1f}s of {z["seconds"]:g}s'
            elif z['kind'] == 'entry':
                if members:
                    if z['_since'] is None or t - z['_last'] > EXIT_GRACE: z['_since'] = t
                    z['_last'] = t
                    if t - z['_since'] >= z['seconds']:
                        z['_fired'] = t
                        for o in members: o['level'] = z['level']; o['label'] = z.get('object_label', z['on_text'])
                if t - z['_fired'] <= z['latch']: level, text = z['level'], z['on_text']  # stays up briefly after the zone empties
            elif z['kind'] == 'occupancy':
                n = len(members); text = f'{n} of {z["limit"]}'
                if n > z['limit']:
                    if z['_over'] is None: z['_over'] = t
                    if t - z['_over'] >= z.get('hold', 1.0):
                        level, text = 'alert', f'{n} of {z["limit"]} · OVER'
                        for o in members: o['level'] = 'alert'; o['label'] = 'QUEUE'
                else: z['_over'] = None
            if level != z['_prev']:
                if level != 'ok' or z['_prev'] != 'ok':
                    self.events.append({'t': round(t, 2), 'zone': z['name'], 'level': level, 'text': text if level != 'ok' else 'cleared',
                                   'event_text': z.get('event_text', text) if level != 'ok' else 'cleared'})
                z['_prev'] = level
            zrows.append({'name': z['name'], 'level': level, 'text': text})
        return {'t': round(t, 3), 'zones': zrows,
                    'objects': [{'id': o['id'], 'kind': o['kind'], 'box': [round(v) for v in o['box']], 'level': o['level'], 'label': o['label']} for o in objs]}


def main(det_path, scene_path, out_path):
    D = json.load(open(det_path)); SC = json.load(open(scene_path)); fps = D['fps']
    zones = SC['zones']; R = ZoneRules(zones)
    frames = [R.step(raw, fi / fps) for fi, raw in enumerate(D['frames'])]; events = R.events
    json.dump({'fps': fps, 'width': D['width'], 'height': D['height'], 'model': D['model'], 'scene': SC['scene'], 'panel': SC.get('panel', 'tl'),
               'count_label': SC.get('count_label', 'People'), 'count_kind': SC.get('count_kind', 'person'),
               'tagline': SC.get('tagline'), 'zones': [{'name': z['name'], 'kind': z['kind'], 'poly': z['poly'], 'label_at': z.get('label_at')} for z in zones], 'frames': frames, 'events': events}, open(out_path, 'w'))
    for e in events: print(e)

if __name__ == '__main__': main(*sys.argv[1:4])
