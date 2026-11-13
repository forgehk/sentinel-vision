"""Render the desk-status overlay onto the clip.

    python render.py clip_graded.mp4 states.json out_landscape.mp4 --layout landscape
    python render.py clip_graded.mp4 states.json out_vertical.mp4  --layout vertical

Everything drawn comes from states.json (model detections + the rules in analyze.py).
"""
import argparse, json, os, subprocess
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_HERE = os.path.dirname(os.path.abspath(__file__))
# Inter is looked for beside this file first, so a packaged copy needs no system fonts. An app can also set FONT_DIR itself.
FONT_DIR = next((d for d in (os.path.join(_HERE, 'fonts'), '/usr/share/fonts/opentype/inter') if os.path.isdir(d)), os.path.join(_HERE, 'fonts'))
def font(weight, size): return ImageFont.truetype(os.path.join(FONT_DIR, f'Inter-{weight}.otf'), int(round(size)))

GREEN, GREEN_DK = (34, 197, 94), (21, 128, 61)
RED, RED_DK = (239, 68, 68), (198, 40, 40)
AMBER = (251, 191, 36)
GREY = (203, 213, 225)
INK = (8, 13, 20)
STATUS_COLOR = {'WORKING': (GREEN, GREEN_DK), 'ABSENT': (RED, RED_DK), 'PHONE USAGE': (RED, RED_DK)}
EVENT_TEXT = {'ABSENT': 'away from desk', 'PHONE USAGE': 'phone in hand', 'WORKING': 'back at desk'}
SMOOTH = 0.55          # EMA weight of the newest box
TOAST_SECONDS = 2.4
FLASH_SECONDS = 0.5


def mix(a, b, q): return tuple(int(round(x + (y - x) * q)) for x, y in zip(a, b))


def chip(d, x, y, text, f, bg, fg=(255, 255, 255), pad=(10, 6), radius=6, anchor='lb'):
    """Filled label. anchor 'lb' = (x, y) is the chip's bottom-left corner. Returns its box."""
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    w, h = r - l + pad[0] * 2, f.size + pad[1] * 2
    x0, y0 = (x, y - h) if anchor == 'lb' else (x, y)
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=radius, fill=bg)
    d.text((x0 + pad[0], y0 + pad[1] + f.size * 0.5), text, font=f, fill=fg, anchor='lm')
    return [x0, y0, x0 + w, y0 + h]


def crest(d, cx, cy, r, color):
    pts = [(cx + r * np.cos(np.pi / 2 + i * np.pi / 3), cy - r * np.sin(np.pi / 2 + i * np.pi / 3)) for i in range(6)]
    d.polygon(pts, outline=color, width=max(2, int(r * 0.13)))
    d.line([(cx - r * .42, cy + r * .02), (cx - r * .1, cy + r * .34), (cx + r * .44, cy - r * .32)], fill=color, width=max(2, int(r * 0.15)), joint='curve')


class Scene:
    """Per-frame geometry with temporal smoothing, shared by both layouts."""
    def __init__(self, states):
        self.S = states; self.fps = states['fps']
        self.zones = {s['id']: s['zone'] for s in states['seats']}
        self.smooth = {}; self.phone_smooth = {}
        self.events = states['events']

    def frame(self, i):
        fr = self.S['frames'][i]; t = fr['t']; desks = []
        for dk in fr['desks']:
            p = dk['person']
            if p is None: self.smooth.pop(dk['id'], None)
            else:
                prev = self.smooth.get(dk['id'])
                self.smooth[dk['id']] = p if prev is None else [SMOOTH * a + (1 - SMOOTH) * b for a, b in zip(p, prev)]
            q = dk['phone'] if dk['status'] == 'PHONE USAGE' else None
            if q is None: self.phone_smooth.pop(dk['id'], None)
            else:
                prev = self.phone_smooth.get(dk['id'])
                self.phone_smooth[dk['id']] = q if prev is None else [SMOOTH * a + (1 - SMOOTH) * b for a, b in zip(q, prev)]
            last = max((e['t'] for e in self.events if e['id'] == dk['id'] and e['t'] <= t), default=None)
            desks.append({'id': dk['id'], 'status': dk['status'], 'zone': self.zones[dk['id']], 'person': self.smooth.get(dk['id']),
                          'phone': self.phone_smooth.get(dk['id']), 'flash': last is not None and t - last < FLASH_SECONDS,
                          'since': None if last is None else t - last})
        toasts = [e for e in self.events if 0 <= t - e['t'] < TOAST_SECONDS]
        return t, desks, fr['unassigned'], toasts


def draw_boxes(img, desks, unassigned, k, label_font, small_font, full_labels=True):
    """Zones, person boxes, phone boxes. k scales source pixels to canvas pixels."""
    fill = Image.new('RGBA', img.size, (0, 0, 0, 0)); fd = ImageDraw.Draw(fill)
    for dk in desks:
        c, _ = STATUS_COLOR[dk['status']]
        z = [v * k for v in dk['zone']]
        fd.rounded_rectangle(z, radius=10 * k, fill=(*c, 78 if dk['status'] != 'WORKING' else 34))
    img.alpha_composite(fill)
    d = ImageDraw.Draw(img)
    for u in unassigned:
        b = [v * k for v in u]
        d.rectangle(b, outline=(*GREY, 210), width=max(2, int(round(3 * k))))
        if full_labels: chip(d, b[0], b[1], 'PERSON', small_font, (71, 85, 105, 235))
    # draw back-to-front so nearer desks sit on top
    for dk in sorted(desks, key=lambda q: q['zone'][3]):
        c, cdk = STATUS_COLOR[dk['status']]
        z = [v * k for v in dk['zone']]
        d.rounded_rectangle(z, radius=10 * k, outline=(*c, 190), width=max(2, int(round(2.5 * k))))
        w = max(3, int(round((7 if dk['flash'] else 4.5) * k)))
        anchor = z
        if dk['person'] is not None:
            b = [v * k for v in dk['person']]
            d.rectangle(b, outline=(*c, 255), width=w); anchor = b
        text = f"ID {dk['id']} · {dk['status']}" if full_labels else f"ID {dk['id']}"
        chip(d, anchor[0] - w // 2, max(label_font.size + 14, anchor[1]), text, label_font, (*cdk, 245))
        if dk['phone'] is not None:
            b = [v * k for v in dk['phone']]; g = 6 * k
            b = [b[0] - g, b[1] - g, b[2] + g, b[3] + g]
            d.rectangle(b, outline=(*AMBER, 255), width=max(3, int(round(4 * k))))
            if full_labels: chip(d, b[0], b[3] + small_font.size + 14, 'PHONE', small_font, (*AMBER, 245), fg=(40, 26, 0))


def panel_landscape(img, t, desks, toasts, F):
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    x, y, w = 36, 36, 372; row = 38; h = 104 + row * len(desks) + 62; A = 222
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=(*INK, A), outline=(70, 84, 102, A), width=2)
    crest(d, x + 38, y + 38, 15, (115, 229, 195, 255))
    d.text((x + 64, y + 38), 'SENTINEL VISION', font=F['brand'], fill=(240, 246, 250, 255), anchor='lm')
    d.ellipse([x + w - 78, y + 32, x + w - 66, y + 44], fill=RED + (255,) if int(t * 2) % 2 == 0 else mix(INK, RED, .35) + (255,))
    d.text((x + w - 58, y + 38), 'LIVE', font=F['tiny'], fill=(226, 232, 240, 255), anchor='lm')
    d.text((x + 24, y + 78), f'Desk activity  ·  t = {t:05.1f}s', font=F['sub'], fill=(148, 163, 184, 255), anchor='lm')
    yy = y + 104
    for dk in desks:
        c, _ = STATUS_COLOR[dk['status']]
        if dk['flash']: d.rounded_rectangle([x + 12, yy - 1, x + w - 12, yy + row - 5], radius=9, fill=mix(INK, c, .28) + (A,))
        d.ellipse([x + 24, yy + 8, x + 42, yy + 26], fill=c + (255,))
        d.text((x + 56, yy + 17), f"ID {dk['id']}", font=F['row'], fill=(226, 232, 240, 255), anchor='lm')
        d.text((x + 114, yy + 17), dk['status'], font=F['rowb'], fill=c + (255,), anchor='lm')
        yy += row
    d.line([x + 24, yy + 6, x + w - 24, yy + 6], fill=(70, 84, 102, 255), width=2)
    working = sum(q['status'] == 'WORKING' for q in desks); alerts = len(desks) - working
    d.text((x + 24, yy + 34), 'Working', font=F['sub'], fill=(203, 213, 225, 255), anchor='lm')
    d.text((x + 104, yy + 34), str(working), font=F['num'], fill=GREEN + (255,), anchor='lm')
    d.text((x + 168, yy + 34), 'Alerts', font=F['sub'], fill=(203, 213, 225, 255), anchor='lm')
    d.text((x + 226, yy + 34), str(alerts), font=F['num'], fill=(RED if alerts else GREY) + (255,), anchor='lm')
    img.alpha_composite(layer)
    # toast: newest status change, bottom centre
    if toasts:
        e = toasts[-1]; age = t - e['t']
        ease = min(1, age / .25); fade = min(1, (TOAST_SECONDS - age) / .35)
        text = f"ID {e['id']}  ·  {EVENT_TEXT[e['to']]}"; c = STATUS_COLOR[e['to']][0]
        tl = Image.new('RGBA', img.size, (0, 0, 0, 0)); td = ImageDraw.Draw(tl)
        tw = td.textlength(text, font=F['toast']); bw = tw + 150; bx = (img.width - bw) / 2; by = img.height - 118 + (1 - ease) * 40
        td.rounded_rectangle([bx, by, bx + bw, by + 68], radius=16, fill=(*INK, 235), outline=c + (255,), width=3)
        td.text((bx + 26, by + 34), 'ALERT' if e['to'] != 'WORKING' else 'CLEARED', font=F['tiny'], fill=c + (255,), anchor='lm')
        td.text((bx + 112, by + 34), text, font=F['toast'], fill=(241, 245, 249, 255), anchor='lm')
        alpha = tl.getchannel('A').point(lambda v: int(v * fade * ease)); tl.putalpha(alpha)
        img.alpha_composite(tl)


def compose_vertical(frame_img, t, desks, unassigned, F):
    W, H = 1080, 1920
    if not hasattr(compose_vertical, 'bg'):  # soft vertical gradient, built once
        bg = Image.new('RGBA', (W, H), (*INK, 255)); bd = ImageDraw.Draw(bg)
        for yy in range(H):
            q = yy / H; bd.line([(0, yy), (W, yy)], fill=(int(9 + 7 * q), int(15 + 13 * q), int(22 + 16 * q), 255))
        compose_vertical.bg = bg
    canvas = compose_vertical.bg.copy(); d = ImageDraw.Draw(canvas)
    tw = d.textlength('SENTINEL VISION', font=F['v_brand']); left = (W - (tw + 92)) / 2
    crest(d, left + 32, 196, 32, (115, 229, 195, 255))
    d.text((left + 92, 196), 'SENTINEL VISION', font=F['v_brand'], fill=(240, 246, 250, 255), anchor='lm')
    d.text((W / 2, 276), 'Desk activity analytics  ·  person + phone detection', font=F['v_sub'], fill=(148, 163, 184, 255), anchor='mm')
    vy = 372; vh = round(W * frame_img.height / frame_img.width)
    video = frame_img.resize((W, vh), Image.LANCZOS).convert('RGBA')
    draw_boxes(video, desks, unassigned, W / frame_img.width, F['v_label'], F['v_small'], full_labels=False)
    canvas.alpha_composite(video, (0, vy))
    d.rectangle([0, vy - 3, W, vy], fill=(52, 66, 82, 255)); d.rectangle([0, vy + vh, W, vy + vh + 3], fill=(52, 66, 82, 255))
    d.ellipse([44, vy + vh + 44, 62, vy + vh + 62], fill=RED + (255,) if int(t * 2) % 2 == 0 else mix((14, 24, 34), RED, .35) + (255,))
    d.text((76, vy + vh + 53), f'LIVE  ·  t = {t:05.1f}s', font=F['v_small'], fill=(203, 213, 225, 255), anchor='lm')
    # status cards, two columns in the same left/right arrangement as the desks
    cy0 = vy + vh + 110; cw, ch, gap = 478, 150, 28
    for n, dk in enumerate(desks):
        col, r = n % 2, n // 2
        cx = 48 + col * (cw + gap); cy = cy0 + r * (ch + gap)
        c, _ = STATUS_COLOR[dk['status']]
        d.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=24, fill=mix((14, 24, 34), c, .34 if dk['flash'] else .13) + (255,), outline=c + (255,), width=5 if dk['flash'] else 3)
        d.ellipse([cx + 30, cy + 34, cx + 62, cy + 66], fill=(*c, 255))
        d.text((cx + 80, cy + 50), f"ID {dk['id']}", font=F['v_id'], fill=(226, 232, 240, 255), anchor='lm')
        d.text((cx + 30, cy + 108), dk['status'], font=F['v_status'], fill=(*c, 255), anchor='lm')
    working = sum(q['status'] == 'WORKING' for q in desks); alerts = len(desks) - working
    by = cy0 + 3 * (ch + gap) + 54
    for label, value, color, bx in (('WORKING', working, GREEN, W * .27), ('ALERTS', alerts, RED if alerts else GREY, W * .73)):
        d.text((bx, by + 46), str(value), font=F['v_num'], fill=(*color, 255), anchor='mm')
        d.text((bx, by + 132), label, font=F['v_cap'], fill=(148, 163, 184, 255), anchor='mm')
    d.line([W / 2, by, W / 2, by + 150], fill=(52, 66, 82, 255), width=3)
    return canvas


def fonts():
    return {'brand': font('ExtraBold', 22), 'tiny': font('Bold', 15), 'sub': font('Medium', 17), 'row': font('SemiBold', 20), 'rowb': font('Bold', 20),
            'num': font('ExtraBold', 25), 'toast': font('SemiBold', 26), 'label': font('Bold', 23), 'small': font('Bold', 17),
            'v_brand': font('ExtraBold', 58), 'v_sub': font('Medium', 27), 'v_label': font('Bold', 23), 'v_small': font('SemiBold', 26),
            'v_id': font('SemiBold', 38), 'v_status': font('ExtraBold', 44), 'v_num': font('ExtraBold', 120), 'v_cap': font('Bold', 30)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video'); ap.add_argument('states'); ap.add_argument('out')
    ap.add_argument('--layout', choices=['landscape', 'vertical'], default='landscape')
    ap.add_argument('--crf', type=int, default=19)
    ap.add_argument('--still', type=float, help='write one PNG at this time (seconds) instead of a video')
    a = ap.parse_args()
    states = json.load(open(a.states)); scene = Scene(states)
    cap = cv2.VideoCapture(a.video); fps = states['fps']
    F = fonts()
    size = (states['width'], states['height']) if a.layout == 'landscape' else (1080, 1920)
    proc = None
    if a.still is None:
        proc = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{size[0]}x{size[1]}', '-r', str(fps),
                                 '-i', '-', '-an', '-c:v', 'libx264', '-crf', str(a.crf), '-preset', 'slow', '-pix_fmt', 'yuv420p',
                                 '-movflags', '+faststart', a.out], stdin=subprocess.PIPE)
    n = len(states['frames'])
    for i in range(n):
        ok, bgr = cap.read()
        if not ok: break
        t, desks, unassigned, toasts = scene.frame(i)
        if a.still is not None and t < a.still: continue
        base = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        if a.layout == 'landscape':
            img = base.convert('RGBA')
            draw_boxes(img, desks, unassigned, 1.0, F['label'], F['small'])
            panel_landscape(img, t, desks, toasts, F)
        else:
            img = compose_vertical(base, t, desks, unassigned, F)
        if a.still is not None:
            img.convert('RGB').save(a.out); print('still at', t); return
        proc.stdin.write(img.convert('RGB').tobytes())
    proc.stdin.close(); proc.wait(); print('wrote', a.out, n, 'frames')


if __name__ == '__main__':
    main()
