"""Sentinel Vision, live.

One program, four modes: office, shop, home, exam. It runs the YOLO26 ONNX models in models/ with ONNX Runtime
on a webcam or a video file and applies the same rule classes as the offline pipeline, so what you see here is
what the pipeline computes. Nothing is scripted and nothing leaves the machine.

    python SentinelOffice.py                      start on the sample clip
    python SentinelExam.py --source 0             start on the first webcam
    python SentinelShop.py --source my_clip.mp4   start on a file

Keys: W webcam, O open a video, S sample clip, M switch model, [ and ] input size, Z draw a zone (shop, home),
C clear zones, R reset, P pause, H key hints, F full screen, X screenshot, Q quit.
"""
import argparse, csv, json, math, os, sys, time, traceback

import cv2
import numpy as np
from PIL import Image, ImageDraw

__version__ = '0.1.0'
FROZEN = getattr(sys, 'frozen', False)
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
if not FROZEN: sys.path.insert(0, os.path.join(APP_DIR, '..', 'pipeline'))      # the EXE carries these modules inside it

import render, render_zones, render_exam, analyze, zones_analyze, exam_analyze   # noqa: E402
from render import chip, mix, GREEN, RED, AMBER, GREY, INK                       # noqa: E402

render.FONT_DIR = os.path.join(APP_DIR, 'fonts')
DISPLAY_W = 1920                      # every frame is drawn at this width so the overlay looks the same on any source
SIZES = [640, 960, 1280]
KEYS_TEXT = {'office': 'W webcam    O open video    S sample    M model    [ ] size    R remap seats    P pause    Q quit',
             'exam': 'W webcam    O open video    S sample    M model    [ ] size    R remap seats    P pause    Q quit',
             'shop': 'W webcam    O open video    S sample    M model    [ ] size    Z draw zone    C clear zones    Q quit',
             'home': 'W webcam    O open video    S sample    M model    [ ] size    Z draw zone    C clear zones    Q quit'}
ZONE_RULES = {
    '1': ('Entry, person', {'kind': 'entry', 'target': 'person', 'seconds': 0.35, 'latch': 2.0, 'level': 'alert', 'on_text': 'ENTRY', 'object_label': 'IN ZONE', 'event_text': 'person entered'}),
    '2': ('Dwell over 5 s', {'kind': 'dwell', 'seconds': 5, 'event_text': 'dwell over 5 seconds'}),
    '3': ('More than 2 people', {'kind': 'occupancy', 'limit': 2, 'hold': 0.6, 'event_text': 'over the limit of 2'}),
    '4': ('Vehicle', {'kind': 'entry', 'target': 'vehicle', 'seconds': 0.3, 'latch': 0.5, 'level': 'notice', 'on_text': 'VEHICLE', 'object_label': 'VEHICLE', 'event_text': 'vehicle arrived'}),
    '5': ('Pet, no alert', {'kind': 'entry', 'target': 'pet', 'seconds': 0.4, 'latch': 0.5, 'level': 'info', 'on_text': 'PET · NO ALERT', 'object_label': 'PET · IGNORED', 'event_text': 'pet, no alert'}),
}


def log(*a):
    try:
        with open(os.path.join(APP_DIR, 'sentinel.log'), 'a', encoding='utf-8') as f: f.write(time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a) + '\n')
    except OSError: pass


# ------------------------------------------------------------------------------------------------ models
def open_session(path, prefer):
    """Try the GPU providers this ONNX Runtime build has, then the CPU. A provider that cannot run the graph is skipped."""
    import onnxruntime as ort
    have = ort.get_available_providers()
    order = [p for p in ('DmlExecutionProvider', 'CUDAExecutionProvider') if p in have and prefer != 'cpu'] + ['CPUExecutionProvider']
    last = None
    for prov in order:
        try:
            so = ort.SessionOptions()
            if prov == 'DmlExecutionProvider': so.enable_mem_pattern = False; so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            s = ort.InferenceSession(path, sess_options=so, providers=[prov] if prov == 'CPUExecutionProvider' else [prov, 'CPUExecutionProvider'])
            s.run(None, {s.get_inputs()[0].name: np.zeros((1, 3, 384, 640), np.float32)})          # warm-up, and proof the provider works
            return s, s.get_providers()[0]
        except Exception as e:                                                                        # noqa: BLE001
            last = e; log('provider', prov, 'failed for', os.path.basename(path), repr(e)[:300])
    raise RuntimeError('could not load %s: %r' % (path, last))


PROVIDER_NAME = {'DmlExecutionProvider': 'GPU, DirectML', 'CUDAExecutionProvider': 'GPU, CUDA', 'CPUExecutionProvider': 'CPU'}


class Yolo:
    """A YOLO26 ONNX model with the end-to-end head. Rows come back as x1, y1, x2, y2, confidence, class
    (then 17 keypoints as x, y, confidence for a pose model), in source pixels."""
    def __init__(self, path, prefer='auto'):
        self.path = path; self.name = os.path.splitext(os.path.basename(path))[0].replace('yolo', 'YOLO')
        self.session, self.provider = open_session(path, prefer); self.input = self.session.get_inputs()[0].name; self.ms = 0.0

    def __call__(self, bgr, size, conf):
        h, w = bgr.shape[:2]; g = size / max(h, w); nw, nh = int(round(w * g)), int(round(h * g))
        pw, ph = int(math.ceil(nw / 32) * 32), int(math.ceil(nh / 32) * 32)                           # keep the frame's shape; pad only to a multiple of 32
        canvas = np.full((ph, pw, 3), 114, np.uint8); canvas[:nh, :nw] = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x = np.ascontiguousarray(canvas[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
        t0 = time.perf_counter(); out = self.session.run(None, {self.input: x})[0][0]; self.ms = (time.perf_counter() - t0) * 1000
        out = out[out[:, 4] >= conf].astype(np.float64)
        out[:, :4] /= g
        if out.shape[1] > 6: out[:, 6::3] /= g; out[:, 7::3] /= g
        return out


def iou(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0]); h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0: return 0.0
    return w * h / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - w * h)


class Tracker:
    """Greedy IoU tracker: a detection keeps the ID of the best-overlapping recent track of the same class."""
    def __init__(self, min_iou=0.25, max_age=0.8): self.tracks = {}; self.next = 1; self.min_iou = min_iou; self.max_age = max_age

    def update(self, dets, t):
        """dets: list of (class, box). Returns one track ID per detection."""
        pairs = sorted(((iou(tr['box'], box), tid, i) for i, (c, box) in enumerate(dets) for tid, tr in self.tracks.items() if tr['cls'] == c), reverse=True)
        ids = [None] * len(dets); used = set()
        for score, tid, i in pairs:
            if score < self.min_iou: break
            if ids[i] is None and tid not in used: ids[i] = tid; used.add(tid)
        for i, (c, box) in enumerate(dets):
            if ids[i] is None: ids[i] = self.next; self.next += 1
            self.tracks[ids[i]] = {'cls': c, 'box': box, 't': t}
        for tid in [k for k, v in self.tracks.items() if t - v['t'] > self.max_age]: del self.tracks[tid]
        return ids


# ------------------------------------------------------------------------------------------------ the four modes
class Mode:
    """Shared plumbing. A mode turns model output into a rule state each frame and draws it."""
    name = ''; title = ''; pose = False
    def __init__(self, app): self.app = app; self.w = self.h = 0
    def start(self, w, h): self.w, self.h = w, h; self.tracker = Tracker(); self.events = []; self.objects = 0
    def raw_boxes(self, img, k, boxes, label='PERSON'):
        d = ImageDraw.Draw(img)
        for b in boxes:
            d.rectangle([v * k for v in b], outline=(*GREY, 220), width=3); chip(d, b[0] * k, max(31, b[1] * k), label, self.app.F['small'], (71, 85, 105, 235))


class OfficeMode(Mode):
    name = 'office'; title = 'Desk activity'
    def start(self, w, h):
        super().start(w, h); self.rules = analyze.OfficeRules(w, h); self.buf = []; self.t0 = None; self.scene = None; self.row = None; self.note = 'Mapping seats'

    def process(self, frame, t, dt):
        a = self.app; out = a.det(frame, a.size, 0.08)
        out = [r for r in out if int(r[5]) in (0, 67) and r[4] >= (0.30 if int(r[5]) == 0 else analyze.PHONE_CONF)]
        ids = self.tracker.update([(int(r[5]), list(r[:4])) for r in out], t)
        rows = [[int(r[5]), float(r[4]), *[float(v) for v in r[:4]], tid] for r, tid in zip(out, ids)]
        self.objects = len(rows); self.people = [r[2:6] for r in rows if r[0] == 0]
        if self.scene is None:                                    # still learning where the seats are
            if self.t0 is None: self.t0 = t
            self.buf.append(rows)
            if t - self.t0 >= analyze.CALIB_S:
                seats = self.rules.calibrate(self.buf)
                if seats:
                    self.S = {'fps': 30, 'seats': [{'id': s['id'], 'zone': s['zone']} for s in seats], 'frames': [None], 'events': self.rules.events}
                    self.scene = render.Scene(self.S); self.events = self.rules.events
                else: self.buf = []; self.t0 = None; self.note = 'Nobody seated yet. Sit still for a second'
            return
        self.row = self.rules.step(rows, t, dt)

    def draw(self, img, k, t):
        F = self.app.RF
        if self.scene is None or self.row is None: self.raw_boxes(img, k, self.people); return self.note
        self.S['frames'][0] = self.row; _, desks, unassigned, toasts = self.scene.frame(0)
        render.draw_boxes(img, desks, unassigned, k, F['label'], F['small']); render.panel_landscape(img, t, desks, toasts, F)

    def subject(self, e): return 'ID %d' % e['id'], '%s -> %s' % (e['from'], e['to'])


class ZoneMode(Mode):
    def __init__(self, app, name):
        super().__init__(app); self.name = name; self.title = 'Shop floor' if name == 'shop' else 'Front yard'; self.cfg = None

    def load_zones(self, sample):
        """The sample clip has its own zone file. Any other source uses zones you drew earlier, or one starter zone."""
        w, h = self.w, self.h; self.sample = sample
        if sample: cfg = json.load(open(os.path.join(APP_DIR, 'zones', self.name + '.json'), encoding='utf-8')); cfg.setdefault('width', 1920); cfg.setdefault('height', 1080)
        else:
            path = self.custom_path(); cfg = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else None
            if cfg is None:
                cfg = {'scene': self.title, 'panel': 'tl', 'width': w, 'height': h,
                       'zones': [dict(ZONE_RULES['1'][1], name='Zone 1', anchor='center', poly=[[w * .3, h * .2], [w * .7, h * .2], [w * .7, h * .9], [w * .3, h * .9]])]}
        sx, sy = w / cfg.get('width', w), h / cfg.get('height', h)
        for z in cfg['zones']:
            z['poly'] = [[x * sx, y * sy] for x, y in z['poly']]
            if z.get('label_at'): z['label_at'] = [z['label_at'][0] * sx, z['label_at'][1] * sy]
        cfg['width'], cfg['height'] = w, h; self.set_zones(cfg)

    def custom_path(self): return os.path.join(APP_DIR, 'zones', 'custom_%s.json' % self.name)

    def set_zones(self, cfg):
        self.cfg = cfg; self.rules = zones_analyze.ZoneRules(cfg['zones']); self.events = self.rules.events; self.fr = None
        self.S = {'scene': cfg.get('scene', self.title), 'panel': cfg.get('panel', 'tl'), 'count_label': cfg.get('count_label', 'People'), 'count_kind': cfg.get('count_kind', 'person'),
                  'tagline': cfg.get('tagline', ''), 'zones': [{'name': z['name'], 'kind': z['kind'], 'poly': z['poly'], 'label_at': z.get('label_at')} for z in cfg['zones']],
                  'frames': [None], 'events': self.rules.events}
        self.scene = render_zones.Scene(self.S)

    def plain_zones(self): return [{k: v for k, v in z.items() if not k.startswith('_')} for z in self.cfg['zones']]
    def reset_rules(self): self.set_zones(dict(self.cfg, zones=self.plain_zones()))        # same zones, timers back to zero

    def save_custom(self):
        if self.sample: return                                        # zones drawn on the sample clip last until another source is opened
        clean = dict(self.cfg, zones=self.plain_zones())
        os.makedirs(os.path.dirname(self.custom_path()), exist_ok=True); json.dump(clean, open(self.custom_path(), 'w', encoding='utf-8'), indent=1)

    def add_zone(self, poly, rule_key):
        n = len(self.cfg['zones']) + 1
        zones = self.plain_zones() + [dict(ZONE_RULES[rule_key][1], name='Zone %d' % n, anchor='center', poly=[[float(x), float(y)] for x, y in poly])]
        self.set_zones(dict(self.cfg, zones=zones)); self.save_custom()

    def clear_zones(self): self.set_zones(dict(self.cfg, zones=[])); self.save_custom()

    def start(self, w, h): super().start(w, h); self.fr = None

    def process(self, frame, t, dt):
        a = self.app; out = a.det(frame, a.size, 0.25); out = [r for r in out if int(r[5]) in zones_analyze.KIND]
        ids = self.tracker.update([(int(r[5]), list(r[:4])) for r in out], t)
        rows = [[int(r[5]), float(r[4]), *[float(v) for v in r[:4]], tid] for r, tid in zip(out, ids)]
        self.objects = len(rows); self.fr = self.rules.step(rows, t)

    def draw(self, img, k, t):
        if self.fr is None: return
        F = self.app.ZF; self.S['frames'][0] = self.fr; _, zones, objs, toasts = self.scene.frame(0)
        render_zones.draw_scene(img, zones, objs, k, F); render_zones.panel_landscape(img, self.S, t, zones, objs, toasts, F)
        if not zones: return 'No zones. Press Z to draw one'

    def subject(self, e): return e['zone'], e['event_text']


class ExamMode(Mode):
    name = 'exam'; title = 'Exam hall'; pose = True
    def start(self, w, h):
        super().start(w, h); self.buf = []; self.t0 = None; self.scene = None; self.row = None; self.people = []; self.note = 'Mapping seats'

    def process(self, frame, t, dt):
        a = self.app; out = a.pose(frame, a.size, 0.25)
        ids = self.tracker.update([(0, list(r[:4])) for r in out], t)
        people = [[float(r[4]), *[float(v) for v in r[:4]], tid, [[float(r[6 + i * 3]), float(r[7 + i * 3]), float(r[8 + i * 3])] for i in range(17)]] for r, tid in zip(out, ids)]
        phones = [[float(r[4]), *[float(v) for v in r[:4]]] for r in a.det(frame, a.size, 0.08) if int(r[5]) == 67]
        fr = {'people': people, 'phones': phones}; self.objects = len(people) + len(phones); self.people = [p[1:5] for p in people]
        if self.scene is None:
            if self.t0 is None: self.t0 = t
            self.buf.append(fr)
            if t - self.t0 >= exam_analyze.CALIB_S:
                seats = exam_analyze.calibrate(self.buf, len(self.buf) / exam_analyze.CALIB_S, self.w, self.h)
                if seats:
                    self.rules = exam_analyze.ExamRules(seats); self.events = self.rules.events
                    self.S = {'seats': seats, 'frames': [None], 'events': self.rules.events}; self.scene = render_exam.Scene(self.S)
                else: self.buf = []; self.t0 = None; self.note = 'Nobody seated yet. Sit still for a second'
            return
        self.row = self.rules.step(fr, t, dt)

    def draw(self, img, k, t):
        if self.scene is None or self.row is None: self.raw_boxes(img, k, self.people); return self.note
        F = self.app.EF; self.S['frames'][0] = self.row; _, seats, unassigned, toasts = self.scene.frame(0)
        render_exam.draw_scene(img, seats, unassigned, k, F); render_exam.panel(img, t, seats, toasts, F, 'tr', '', self.row['phones'])

    def subject(self, e): return 'S%d' % e['id'], '%s: %s (risk %d)' % (e['to'], e['text'], e['risk'])


# ------------------------------------------------------------------------------------------------ the app
class App:
    def __init__(self, mode, args):
        self.args = args; self.F = {'small': render.font('Bold', 17), 'hud': render.font('SemiBold', 19), 'hud2': render.font('Medium', 17), 'keys': render.font('SemiBold', 17), 'big': render.font('SemiBold', 28)}
        self.RF, self.ZF, self.EF = render.fonts(), render_zones.fonts(), render_exam.fonts()
        self.mode = {'office': OfficeMode, 'exam': ExamMode}[mode](self) if mode in ('office', 'exam') else ZoneMode(self, mode)
        self.variant = args.model; self.det = self.pose = None; self.load_models(args.model)
        gpu = self.det.provider != 'CPUExecutionProvider'
        self.size = args.imgsz or (1280 if gpu else 640); self.auto_size = not args.imgsz
        self.cap = None; self.kind = None; self.paused = False; self.show_keys_until = 0; self.keys_on = False; self.fullscreen = False
        self.edit = None; self.fps = 0.0; self.t = 0.0; self.logged = 0; self.csv = None; self.frame = None; self.banner = None; self.last_img = None
        self.window = 'Sentinel Vision %s - %s' % (__version__, self.mode.title); self.tick = 0.0; self.pause_at = 0.0; self.first = None

    # ---- models and sources
    def model_path(self, variant, pose): return os.path.join(APP_DIR, 'models', 'yolo26%s%s.onnx' % (variant, '-pose' if pose else ''))
    def load_models(self, variant):
        if not os.path.exists(self.model_path(variant, False)): variant = 'n'
        self.det = Yolo(self.model_path(variant, False), self.args.device)
        self.pose = Yolo(self.model_path(variant, True), self.args.device) if self.mode.pose else None
        self.variant = variant

    def open(self, kind, value=None):
        """kind: 'sample', 'file' or 'cam'."""
        if kind == 'sample': value = os.path.join(APP_DIR, 'samples', self.mode.name + '.mp4')
        cap = cv2.VideoCapture(value, cv2.CAP_DSHOW) if kind == 'cam' and os.name == 'nt' else cv2.VideoCapture(value)
        if kind == 'cam': cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        ok, frame = cap.read()
        if not ok:
            cap.release(); self.banner = ('Camera %s did not open' % value if kind == 'cam' else 'That video could not be opened', time.time() + 4); return False
        if self.cap is not None: self.cap.release()
        self.cap, self.kind, self.value = cap, kind, value; self.first = frame; self.h, self.w = frame.shape[:2]
        self.src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0 if kind != 'cam' else 30.0
        if self.auto_size: self.size = 640 if kind == 'cam' or self.det.provider == 'CPUExecutionProvider' else 1280
        self.restart(new_source=True); self.show_keys_until = time.time() + 9; return True

    def restart(self, new_source=False):
        """Back to time zero: rules, tracker and clocks start again (new source, a loop of the clip, or the R key)."""
        self.mode.start(self.w, self.h)
        if isinstance(self.mode, ZoneMode):
            if new_source: self.mode.load_zones(self.kind == 'sample')
            else: self.mode.reset_rules()
        self.index = 0; self.t = 0.0; self.prev_t = None; self.wall0 = time.time(); self.logged = 0

    def read(self):
        if self.first is not None: frame, self.first = self.first, None; return frame
        if self.kind != 'cam' and not self.args.headless:              # keep a file at real time: wait if we are early, drop frames if we are late
            behind = (time.time() - self.wall0) - self.index / self.src_fps
            if behind < 0: time.sleep(min(0.1, -behind))
            for _ in range(min(60, int(behind * self.src_fps))):
                if self.cap.grab(): self.index += 1
        for _ in range(self.args.every - 1):                           # tests: process every Nth frame, as a slow machine would
            if self.cap.grab(): self.index += 1
        ok, frame = self.cap.read()
        if not ok and self.kind != 'cam':                              # end of the clip: play it again from the top
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0); ok, frame = self.cap.read(); self.restart()
        if ok: self.index += 1
        return frame if ok else None

    # ---- drawing
    def hud(self, img):
        d = ImageDraw.Draw(img); F = self.F; W, H = img.size; m = self.pose if self.mode.pose else self.det
        ms = self.det.ms + (self.pose.ms if self.pose else 0)
        l1 = '%s   %d px   %s' % (m.name + (' + ' + self.det.name if self.pose else ''), self.size, PROVIDER_NAME.get(m.provider, m.provider))
        l2 = '%.0f ms inference   %.0f fps   %d detections' % (ms, self.fps, self.mode.objects)
        w = max(d.textlength(l1, font=F['hud']), d.textlength(l2, font=F['hud2'])) + 44; x, y = W - 36 - w, H - 36 - 72
        if isinstance(self.mode, ZoneMode) and self.mode.S['panel'] == 'br': x = 36
        d.rounded_rectangle([x, y, x + w, y + 72], radius=14, fill=(*INK, 214), outline=(70, 84, 102, 214), width=2)
        d.text((x + 22, y + 24), l1, font=F['hud'], fill=(240, 246, 250, 255), anchor='lm'); d.text((x + 22, y + 50), l2, font=F['hud2'], fill=(148, 163, 184, 255), anchor='lm')

    def pill(self, img, text, y, color=(226, 232, 240), font='keys'):
        d = ImageDraw.Draw(img); f = self.F[font]; w = d.textlength(text, font=f) + 44; x = (img.width - w) / 2; h = f.size + 22
        d.rounded_rectangle([x, y, x + w, y + h], radius=h / 2, fill=(*INK, 220), outline=(70, 84, 102, 220), width=2); d.text((img.width / 2, y + h / 2), text, font=f, fill=(*color, 255), anchor='mm')

    def compose(self, frame):
        k = DISPLAY_W / frame.shape[1]; small = cv2.resize(frame, (DISPLAY_W, int(round(frame.shape[0] * k))), interpolation=cv2.INTER_LINEAR)
        img = Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)).convert('RGBA')
        note = self.mode.draw(img, k, self.t)
        ui = Image.new('RGBA', img.size, (0, 0, 0, 0))                 # the app's own controls go on one clear layer, blended in once
        if self.edit is not None: self.draw_edit(ui, k)
        elif note: self.pill(ui, note, ui.height - 122, font='big')
        self.hud(ui)
        low = isinstance(self.mode, ZoneMode) and self.mode.S['panel'][0] == 'b'      # a bottom panel sends its alerts to the top, so the hints go low
        if self.edit is None and (self.keys_on or time.time() < self.show_keys_until): self.pill(ui, KEYS_TEXT[self.mode.name], ui.height - 76 if low else 30)
        if self.banner and time.time() < self.banner[1]: self.pill(ui, self.banner[0], 130 if low else 92, color=AMBER)
        if self.paused and self.edit is None: self.pill(ui, 'Paused. Press P to carry on', 130 if low else 92)
        img.alpha_composite(ui); return img

    def draw_edit(self, img, k):
        d = ImageDraw.Draw(img); pts = [(x * k, y * k) for x, y in self.edit['pts']]
        if len(pts) >= 3: d.polygon(pts, fill=(*AMBER, 70))
        if len(pts) >= 2: d.line(pts + ([pts[0]] if self.edit['stage'] == 'rule' else []), fill=(*AMBER, 255), width=4, joint='curve')
        for x, y in pts: d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=(*AMBER, 255), outline=(40, 26, 0, 255), width=2)
        y = img.height - 196                                           # above the readout in the corner, whatever the prompt's width
        if self.edit['stage'] == 'points': self.pill(img, 'Click each corner of the zone. Enter when done, Esc to cancel', y, font='big')
        else: self.pill(img, 'Rule for this zone:   ' + '    '.join('%s %s' % (kx, v[0]) for kx, v in ZONE_RULES.items() if self.mode.name == 'home' or kx in '123'), y, font='big')

    # ---- input
    def set_paused(self, on):
        if on and not self.paused: self.pause_at = time.time()
        if not on and self.paused: self.wall0 += time.time() - self.pause_at; self.tick = 0.0       # the stream clock does not run while paused
        self.paused = on

    def on_mouse(self, event, x, y, flags, _):
        if self.edit is None or self.edit['stage'] != 'points' or event != cv2.EVENT_LBUTTONDOWN: return
        k = DISPLAY_W / self.w; self.edit['pts'].append((x / k, y / k))

    def pick_file(self):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
            path = filedialog.askopenfilename(title='Choose a video', filetypes=[('Video', '*.mp4 *.mov *.avi *.mkv *.webm *.m4v'), ('All files', '*.*')]); root.destroy()
            return path or None
        except Exception as e:                                         # noqa: BLE001
            log('file dialog failed', repr(e)); self.banner = ('The file picker is not available. Start with --source <file>', time.time() + 5); return None

    def key(self, c):
        """c: a lower-case character, or 'enter' / 'esc'. Returns False to quit."""
        if self.edit is not None:
            if c == 'esc': self.edit = None; self.set_paused(False)
            elif self.edit['stage'] == 'points' and c == 'enter':
                if len(self.edit['pts']) >= 3: self.edit['stage'] = 'rule'
                else: self.banner = ('A zone needs at least three corners', time.time() + 3)
            elif self.edit['stage'] == 'rule' and c in ZONE_RULES and (self.mode.name == 'home' or c in '123'):
                self.mode.add_zone(self.edit['pts'], c); self.edit = None; self.set_paused(False)
            return True
        if c in ('q', 'esc'): return False
        if c == 'w':
            nxt = (self.value + 1) % 4 if self.kind == 'cam' else 0
            if not self.open('cam', nxt) and nxt: self.open('cam', 0)
        elif c == 'o':
            path = self.pick_file()
            if path: self.open('file', path)
        elif c == 's': self.open('sample')
        elif c == 'm':
            other = 's' if self.variant == 'n' else 'n'
            if os.path.exists(self.model_path(other, False)): self.load_models(other); self.restart()
            else: self.banner = ('Only one model is installed in the models folder', time.time() + 4)
        elif c in ('[', ']'): self.auto_size = False; self.size = SIZES[max(0, min(len(SIZES) - 1, SIZES.index(self.size) + (1 if c == ']' else -1)))] if self.size in SIZES else 640
        elif c == 'r': self.restart()
        elif c in ('p', ' '): self.set_paused(not self.paused)
        elif c == 'h': self.keys_on = not self.keys_on; self.show_keys_until = 0
        elif c == 'f':
            self.fullscreen = not self.fullscreen
            if not self.args.headless: cv2.setWindowProperty(self.window, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN if self.fullscreen else cv2.WINDOW_NORMAL)
        elif c == 'x' and self.last_img is not None:
            os.makedirs(os.path.join(APP_DIR, 'logs'), exist_ok=True); path = os.path.join(APP_DIR, 'logs', '%s_%s.png' % (self.mode.name, time.strftime('%Y%m%d_%H%M%S')))
            self.last_img.convert('RGB').save(path); self.banner = ('Saved ' + os.path.basename(path), time.time() + 3)
        elif isinstance(self.mode, ZoneMode):
            if c == 'z': self.edit = {'pts': [], 'stage': 'points'}; self.set_paused(True)
            elif c == 'c': self.mode.clear_zones()
        return True

    def log_events(self):
        ev = self.mode.events
        if len(ev) <= self.logged: return
        if self.csv is None:
            os.makedirs(os.path.join(APP_DIR, 'logs'), exist_ok=True)
            self.csv_file = open(os.path.join(APP_DIR, 'logs', '%s_%s.csv' % (self.mode.name, time.strftime('%Y%m%d_%H%M%S'))), 'w', newline='', encoding='utf-8')
            self.csv = csv.writer(self.csv_file); self.csv.writerow(['clock', 'seconds_into_stream', 'source', 'subject', 'event'])
        for e in ev[self.logged:]:
            who, what = self.mode.subject(e); self.csv.writerow([time.strftime('%H:%M:%S'), e['t'], self.kind if self.kind != 'file' else os.path.basename(str(self.value)), who, what])
        self.csv_file.flush(); self.logged = len(ev)

    # ---- the loop
    def step(self):
        """Read, detect, apply the rules, draw. Returns the composed picture (PIL, RGBA)."""
        if not self.paused or self.frame is None:
            frame = self.read()
            if frame is None: return self.last_img
            self.frame = frame
            self.t = (time.time() - self.wall0) if self.kind == 'cam' else self.index / self.src_fps
            dt = 1.0 / self.src_fps if self.prev_t is None else max(1e-3, self.t - self.prev_t); self.prev_t = self.t
            self.mode.process(frame, self.t, dt); self.log_events()
            now = time.time()
            if self.tick: inst = 1.0 / max(1e-3, now - self.tick); self.fps = inst if not self.fps else 0.9 * self.fps + 0.1 * inst
            self.tick = now
        self.last_img = self.compose(self.frame); return self.last_img

    def run(self):
        a = self.args; src = a.source
        if src is None: self.open('sample')
        elif str(src).isdigit(): self.open('cam', int(src)) or self.open('sample')
        else: self.open('file', src) or self.open('sample')
        if self.cap is None: raise RuntimeError('no video source could be opened (looked for samples/%s.mp4)' % self.mode.name)
        script = dict(s.split(':', 1) for s in a.script.split(',')) if a.script else {}
        writer = None; n = 0
        if not a.headless:
            cv2.namedWindow(self.window, cv2.WINDOW_NORMAL); cv2.resizeWindow(self.window, 1280, 720); cv2.setMouseCallback(self.window, self.on_mouse)
        while True:
            img = self.step(); n += 1
            if img is not None:
                bgr = cv2.cvtColor(np.asarray(img.convert('RGB')), cv2.COLOR_RGB2BGR)
                if a.save:
                    if writer is None: writer = cv2.VideoWriter(a.save, cv2.VideoWriter_fourcc(*'mp4v'), 24, (bgr.shape[1], bgr.shape[0]))
                    writer.write(bgr)
                if a.stills and n in a.stills: img.convert('RGB').save(os.path.join(a.stills_dir, '%s_%04d.jpg' % (self.mode.name, n)), quality=88)
                if not a.headless: cv2.imshow(self.window, bgr)
            code = -1 if a.headless else cv2.waitKey(1 if not self.paused else 30)
            c = {13: 'enter', 10: 'enter', 27: 'esc'}.get(code & 0xFF, chr(code & 0xFF).lower()) if code != -1 else None
            if str(n) in script:                                        # scripted input, used by the tests
                s = script[str(n)]
                if s.startswith('click'): _, x, y = s.split('@'); self.on_mouse(cv2.EVENT_LBUTTONDOWN, int(x), int(y), 0, None); c = None
                else: c = s
            if c is not None and not self.key(c): break
            if not a.headless and cv2.getWindowProperty(self.window, cv2.WND_PROP_VISIBLE) < 1: break       # the window was closed
            if a.max_frames and n >= a.max_frames: break
        if writer is not None: writer.release()
        if self.cap is not None: self.cap.release()
        if not a.headless: cv2.destroyAllWindows()


def main(mode):
    ap = argparse.ArgumentParser(description='Sentinel Vision live: ' + mode)
    ap.add_argument('--source', help='a video file, or a camera number such as 0. Default: the sample clip')
    ap.add_argument('--model', choices=['n', 's'], default='s', help='n = fastest, s = more accurate (default)')
    ap.add_argument('--imgsz', type=int, choices=SIZES, help='model input width. Default: 1280 on a GPU, 640 on a CPU or a webcam')
    ap.add_argument('--device', choices=['auto', 'cpu'], default='auto')
    ap.add_argument('--headless', action='store_true', help='no window (for tests and for saving a video)')
    ap.add_argument('--save', help='write the annotated video to this .mp4'); ap.add_argument('--max-frames', type=int, default=0)
    ap.add_argument('--stills', type=lambda s: {int(x) for x in s.split(',')}, help=argparse.SUPPRESS); ap.add_argument('--stills-dir', default='.', help=argparse.SUPPRESS)
    ap.add_argument('--version', action='version', version='Sentinel Vision ' + __version__)
    ap.add_argument('--script', help=argparse.SUPPRESS); ap.add_argument('--every', type=int, default=1, help=argparse.SUPPRESS)
    ap.add_argument('--report', action='store_true', help=argparse.SUPPRESS); ap.add_argument('--report-file', help=argparse.SUPPRESS)
    args = ap.parse_args()
    try:
        app = App(mode, args); app.run()
        if getattr(app, 'csv', None) is not None: app.csv_file.close()
        if args.report or args.report_file:                             # a plain-text summary of the run, for the tests and the release check
            seats = len(getattr(getattr(app.mode, 'rules', None), 'seats', []) or [])
            lines = ['REPORT %s version=%s model=%s size=%d provider=%s seats=%d ms=%.0f' % (mode, __version__, app.variant, app.size, app.det.provider, seats, app.det.ms + (app.pose.ms if app.pose else 0))]
            lines += ['   %6.2fs  %s  %s' % ((e['t'],) + tuple(app.mode.subject(e))) for e in app.mode.events]
            if args.report: print('\n'.join(lines))
            if args.report_file:
                with open(args.report_file, 'w', encoding='utf-8') as f: f.write('\n'.join(lines) + '\n')
    except Exception:                                                  # noqa: BLE001
        text = traceback.format_exc(); log(text)
        if FROZEN and os.name == 'nt' and '--headless' not in sys.argv:   # a windowed EXE has no console to print to
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text[-1500:] + '\n\nDetails are in sentinel.log next to the program.', 'Sentinel Vision could not start', 0x10)
        raise


if __name__ == '__main__':
    main(sys.argv.pop(1) if len(sys.argv) > 1 and sys.argv[1] in ('office', 'shop', 'home', 'exam') else 'office')
