"""Render the zone-status overlay (shop floor, home, any scene described by zones).

    python render_zones.py clip_graded.mp4 states.json out.mp4 --layout landscape|vertical [--still 5.0]
"""
import argparse, json, subprocess
import cv2
from PIL import Image, ImageDraw
from render import chip, crest, font, mix, GREEN, GREEN_DK, RED, RED_DK, AMBER, GREY, INK, SMOOTH, TOAST_SECONDS, FLASH_SECONDS

AMBER_DK = (176, 118, 0)
LEVEL = {'ok': (GREEN, GREEN_DK), 'info': (GREEN, GREEN_DK), 'alert': (RED, RED_DK), 'notice': (AMBER, AMBER_DK)}


class Scene:
    def __init__(self, S):
        self.S = S; self.smooth = {}

    def frame(self, i):
        fr = self.S['frames'][i]; t = fr['t']; seen = set(); objs = []
        events = [e for e in self.S['events'] if e['level'] != 'ok']       # read each frame, so a live run can keep appending
        for o in fr['objects']:
            key = (o['kind'], o['id']) if o['id'] >= 0 else None
            box = o['box']
            if key is not None:
                prev = self.smooth.get(key)
                box = box if prev is None else [SMOOTH * a + (1 - SMOOTH) * b for a, b in zip(box, prev)]
                self.smooth[key] = box; seen.add(key)
            objs.append({**o, 'box': box})
        for k in [k for k in self.smooth if k not in seen]: del self.smooth[k]
        zones = []
        for z, zdef in zip(fr['zones'], self.S['zones']):
            last = max((e['t'] for e in events if e['zone'] == z['name'] and e['t'] <= t), default=None)
            zones.append({**z, 'poly': zdef['poly'], 'label_at': zdef.get('label_at'), 'flash': last is not None and t - last < FLASH_SECONDS})
        toasts = [e for e in events if e['level'] in ('alert', 'notice') and 0 <= t - e['t'] < TOAST_SECONDS]
        return t, zones, objs, toasts


def draw_scene(img, zones, objs, k, F, full_labels=True):
    fill = Image.new('RGBA', img.size, (0, 0, 0, 0)); fd = ImageDraw.Draw(fill)
    for z in zones:
        c, _ = LEVEL[z['level']]
        fd.polygon([(x * k, y * k) for x, y in z['poly']], fill=(*c, {'ok': 30, 'info': 44, 'notice': 58, 'alert': 82}[z['level']]))
    img.alpha_composite(fill)
    d = ImageDraw.Draw(img)
    for z in zones:
        c, cdk = LEVEL[z['level']]
        pts = [(x * k, y * k) for x, y in z['poly']]
        d.line(pts + [pts[0]], fill=(*c, 235), width=max(2, int(round((5 if z['flash'] else 3) * k))), joint='curve')
        top = (z['label_at'][0] * k, z['label_at'][1] * k) if z.get('label_at') else min(pts, key=lambda p: (p[1], p[0]))
        chip(d, top[0], max(F['zone'].size + 14, top[1]), z['name'].upper(), F['zone'], (*cdk, 245))
    for o in sorted(objs, key=lambda q: q['box'][3]):
        c, cdk = LEVEL[o['level']]
        b = [v * k for v in o['box']]
        strong = o['level'] in ('alert', 'notice')
        w = max(2, int(round((4.5 if strong else 3) * k)))
        d.rectangle(b, outline=(*c, 255), width=w)
        if full_labels or strong:
            f = F['label'] if strong else F['small']
            chip(d, b[0] - w // 2, max(f.size + 14, b[1]), o['label'], f, (*cdk, 245), pad=(10, 6) if strong else (8, 5))


def panel_landscape(img, S, t, zones, objs, toasts, F):
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    w = 452; row = 40; h = 104 + row * len(zones) + 62; A = 222; m = 36
    x = m if S['panel'][1] == 'l' else img.width - m - w
    y = m if S['panel'][0] == 't' else img.height - m - h
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=(*INK, A), outline=(70, 84, 102, A), width=2)
    crest(d, x + 38, y + 38, 15, (115, 229, 195, 255))
    d.text((x + 64, y + 38), 'SENTINEL VISION', font=F['brand'], fill=(240, 246, 250, 255), anchor='lm')
    d.ellipse([x + w - 78, y + 32, x + w - 66, y + 44], fill=RED + (255,) if int(t * 2) % 2 == 0 else mix(INK, RED, .35) + (255,))
    d.text((x + w - 58, y + 38), 'LIVE', font=F['tiny'], fill=(226, 232, 240, 255), anchor='lm')
    d.text((x + 24, y + 78), f"{S['scene']}  ·  t = {t:05.1f}s", font=F['sub'], fill=(148, 163, 184, 255), anchor='lm')
    yy = y + 104
    for z in zones:
        c, _ = LEVEL[z['level']]
        if z['flash']: d.rounded_rectangle([x + 12, yy - 1, x + w - 12, yy + row - 5], radius=9, fill=mix(INK, c, .28) + (A,))
        d.ellipse([x + 24, yy + 9, x + 42, yy + 27], fill=c + (255,))
        d.text((x + 56, yy + 18), z['name'], font=F['row'], fill=(226, 232, 240, 255), anchor='lm')
        d.text((x + w - 24, yy + 18), z['text'], font=F['rowb'], fill=c + (255,), anchor='rm')
        yy += row
    d.line([x + 24, yy + 6, x + w - 24, yy + 6], fill=(70, 84, 102, 255), width=2)
    count = sum(o['kind'] == S['count_kind'] for o in objs); alerts = sum(z['level'] == 'alert' for z in zones)
    d.text((x + 24, yy + 34), S['count_label'], font=F['sub'], fill=(203, 213, 225, 255), anchor='lm')
    lw = d.textlength(S['count_label'], font=F['sub'])
    d.text((x + 34 + lw, yy + 34), str(count), font=F['num'], fill=(240, 246, 250, 255), anchor='lm')
    d.text((x + 34 + lw + 62, yy + 34), 'Alerts', font=F['sub'], fill=(203, 213, 225, 255), anchor='lm')
    d.text((x + 34 + lw + 120, yy + 34), str(alerts), font=F['num'], fill=(RED if alerts else GREY) + (255,), anchor='lm')
    img.alpha_composite(layer)
    if toasts:
        e = toasts[-1]; age = t - e['t']
        ease = min(1, age / .25); fade = min(1, (TOAST_SECONDS - age) / .35); c = LEVEL[e['level']][0]
        text = f"{e['zone']}  ·  {e['event_text']}"
        tl = Image.new('RGBA', img.size, (0, 0, 0, 0)); td = ImageDraw.Draw(tl)
        tag = 'ALERT' if e['level'] == 'alert' else 'NOTICE'
        tw = td.textlength(text, font=F['toast']); bw = tw + 162
        # keep the toast clear of a bottom-anchored panel
        bx = (img.width - bw) / 2; by = (img.height - 118 if S['panel'][0] == 't' else 50) + (1 - ease) * (40 if S['panel'][0] == 't' else -40)
        td.rounded_rectangle([bx, by, bx + bw, by + 68], radius=16, fill=(*INK, 235), outline=c + (255,), width=3)
        td.text((bx + 26, by + 34), tag, font=F['tiny'], fill=c + (255,), anchor='lm')
        td.text((bx + 124, by + 34), text, font=F['toast'], fill=(241, 245, 249, 255), anchor='lm')
        tl.putalpha(tl.getchannel('A').point(lambda v: int(v * fade * ease)))
        img.alpha_composite(tl)


def compose_vertical(frame_img, S, t, zones, objs, F):
    W, H = 1080, 1920
    if not hasattr(compose_vertical, 'bg'):
        bg = Image.new('RGBA', (W, H), (*INK, 255)); bd = ImageDraw.Draw(bg)
        for yy in range(H):
            q = yy / H; bd.line([(0, yy), (W, yy)], fill=(int(9 + 7 * q), int(15 + 13 * q), int(22 + 16 * q), 255))
        compose_vertical.bg = bg
    canvas = compose_vertical.bg.copy(); d = ImageDraw.Draw(canvas)
    tw = d.textlength('SENTINEL VISION', font=F['v_brand']); left = (W - (tw + 92)) / 2
    crest(d, left + 32, 196, 32, (115, 229, 195, 255))
    d.text((left + 92, 196), 'SENTINEL VISION', font=F['v_brand'], fill=(240, 246, 250, 255), anchor='lm')
    d.text((W / 2, 276), S['tagline'], font=F['v_sub'], fill=(148, 163, 184, 255), anchor='mm')
    vy = 372; vh = round(W * frame_img.height / frame_img.width)
    video = frame_img.resize((W, vh), Image.LANCZOS).convert('RGBA')
    draw_scene(video, zones, objs, W / frame_img.width, F, full_labels=False)
    canvas.alpha_composite(video, (0, vy))
    d.rectangle([0, vy - 3, W, vy], fill=(52, 66, 82, 255)); d.rectangle([0, vy + vh, W, vy + vh + 3], fill=(52, 66, 82, 255))
    d.ellipse([44, vy + vh + 44, 62, vy + vh + 62], fill=RED + (255,) if int(t * 2) % 2 == 0 else mix((14, 24, 34), RED, .35) + (255,))
    d.text((76, vy + vh + 53), f"LIVE  ·  {S['scene']}  ·  t = {t:05.1f}s", font=F['v_small'], fill=(203, 213, 225, 255), anchor='lm')
    cy0 = vy + vh + 110; ch, gap = 150, 28
    for n, z in enumerate(zones):
        cx = 48; cy = cy0 + n * (ch + gap); c, _ = LEVEL[z['level']]
        d.rounded_rectangle([cx, cy, W - 48, cy + ch], radius=24, fill=mix((14, 24, 34), c, .34 if z['flash'] else .13) + (255,), outline=c + (255,), width=5 if z['flash'] else 3)
        d.ellipse([cx + 30, cy + 34, cx + 62, cy + 66], fill=c + (255,))
        d.text((cx + 80, cy + 50), z['name'], font=F['v_id'], fill=(226, 232, 240, 255), anchor='lm')
        d.text((cx + 30, cy + 108), z['text'], font=F['v_status'], fill=c + (255,), anchor='lm')
    count = sum(o['kind'] == S['count_kind'] for o in objs); alerts = sum(z['level'] == 'alert' for z in zones)
    by = cy0 + len(zones) * (ch + gap) + 54
    for label, value, color, bx in ((S['count_label'].upper(), count, (240, 246, 250), W * .27), ('ALERTS', alerts, RED if alerts else GREY, W * .73)):
        d.text((bx, by + 46), str(value), font=F['v_num'], fill=color + (255,), anchor='mm')
        d.text((bx, by + 132), label, font=F['v_cap'], fill=(148, 163, 184, 255), anchor='mm')
    d.line([W / 2, by, W / 2, by + 150], fill=(52, 66, 82, 255), width=3)
    return canvas


def fonts():
    return {'brand': font('ExtraBold', 22), 'tiny': font('Bold', 15), 'sub': font('Medium', 17), 'row': font('SemiBold', 20), 'rowb': font('Bold', 20),
            'num': font('ExtraBold', 25), 'toast': font('SemiBold', 26), 'label': font('Bold', 23), 'small': font('Bold', 16), 'zone': font('Bold', 19),
            'v_brand': font('ExtraBold', 58), 'v_sub': font('Medium', 27), 'v_small': font('SemiBold', 26),
            'v_id': font('SemiBold', 38), 'v_status': font('ExtraBold', 44), 'v_num': font('ExtraBold', 120), 'v_cap': font('Bold', 30)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video'); ap.add_argument('states'); ap.add_argument('out')
    ap.add_argument('--layout', choices=['landscape', 'vertical'], default='landscape')
    ap.add_argument('--crf', type=int, default=23); ap.add_argument('--still', type=float)
    ap.add_argument('--plain', action='store_true', help='no panel or toast (boxes and zones only)')
    a = ap.parse_args()
    S = json.load(open(a.states)); S['tagline'] = S.get('tagline') or 'Zone analytics  ·  people, vehicles and pets'; scene = Scene(S)
    cap = cv2.VideoCapture(a.video); fps = S['fps']
    F = fonts()
    FV = dict(F, label=font('Bold', 22), small=font('Bold', 16), zone=font('Bold', 18))
    size = (S['width'], S['height']) if a.layout == 'landscape' else (1080, 1920)
    proc = None
    if a.still is None:
        proc = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{size[0]}x{size[1]}', '-r', str(fps),
                                 '-i', '-', '-an', '-c:v', 'libx264', '-crf', str(a.crf), '-preset', 'slow', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', a.out], stdin=subprocess.PIPE)
    for i in range(len(S['frames'])):
        ok, bgr = cap.read()
        if not ok: break
        t, zones, objs, toasts = scene.frame(i)
        if a.still is not None and t < a.still: continue
        base = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        if a.layout == 'landscape':
            img = base.convert('RGBA'); draw_scene(img, zones, objs, 1.0, F)
            if not a.plain: panel_landscape(img, S, t, zones, objs, toasts, F)
        else:
            img = compose_vertical(base, S, t, zones, objs, FV)
        if a.still is not None:
            img.convert('RGB').save(a.out); print('still at', t); return
        proc.stdin.write(img.convert('RGB').tobytes())
    proc.stdin.close(); proc.wait(); print('wrote', a.out)


if __name__ == '__main__': main()
