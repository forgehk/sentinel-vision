"""Render the exam-hall overlay onto the clip.

    python render_exam.py clip_graded.mp4 states.json out.mp4 --layout landscape|vertical [--still 5.2]

Everything drawn comes from states.json (pose + phone detections and the rules in exam_analyze.py).
"""
import argparse, json, math, subprocess
import cv2
from PIL import Image, ImageDraw
from render import chip, crest, font, mix, GREEN, GREEN_DK, RED, RED_DK, AMBER, GREY, INK

AMBER_DK = (176, 118, 0)
SKY = (56, 189, 248)
COLOR = {'NORMAL': (GREEN, GREEN_DK), 'REVIEW': (AMBER, AMBER_DK), 'FLAGGED': (RED, RED_DK)}
SMOOTH = 0.55; TOAST_SECONDS = 2.6; FLASH_SECONDS = 0.5; HOLD_SECONDS = 0.75
NEAR_RX = 85            # desk zones at least this wide (pixels) get the full label and the head-direction line


def note(row):
    if row['person'] is None: return 'seat empty'
    if row['phone'] is not None and row['target'] in ('own', 'away', None): return 'phone at the desk'
    if row['target'] is None: return 'head not visible'
    yaw = 'yaw %+d°' % row['yaw']
    if row['target'] == 'own': return 'own paper  ' + yaw
    if row['target'] == 'away': return 'looking away  ' + yaw
    return '→ desk S%d  %s' % (row['target'], yaw)


class Scene:
    def __init__(self, S):
        self.S = S; self.zones = {s['id']: s['zone'] for s in S['seats']}; self.smooth = {}; self.seen = {}; self.last = {}; self.events = S['events']

    def frame(self, i):
        fr = self.S['frames'][i]; t = fr['t']; seats = []
        for r in fr['seats']:
            p = r['person']
            if p is None:
                if t - self.seen.get(r['id'], -9) > HOLD_SECONDS: self.smooth.pop(r['id'], None)
                else: r = dict(self.last[r['id']], status=r['status'], risk=r['risk'], phone=r['phone'])     # hidden for a moment: keep the last reading
            else:
                self.seen[r['id']] = t; self.last[r['id']] = r
                prev = self.smooth.get(r['id']); self.smooth[r['id']] = p if prev is None else [SMOOTH * a + (1 - SMOOTH) * b for a, b in zip(p, prev)]
            last = max((e['t'] for e in self.events if e['id'] == r['id'] and e['t'] <= t), default=None)
            seats.append(dict(r, box=self.smooth.get(r['id']), zone=self.zones[r['id']], flash=last is not None and t - last < FLASH_SECONDS))
        return t, seats, fr['unassigned'], [e for e in self.events if 0 <= t - e['t'] < TOAST_SECONDS]


def arrow(d, x0, y0, x1, y1, color, w):
    """A line with a head at (x1, y1), drawn over a slightly wider dark stroke so it reads on any background."""
    ang = math.atan2(y1 - y0, x1 - x0); L = 5.2 * w
    bx, by = x1 - math.cos(ang) * L * 0.8, y1 - math.sin(ang) * L * 0.8
    head = [(x1, y1), (x1 - math.cos(ang - 0.42) * L, y1 - math.sin(ang - 0.42) * L), (x1 - math.cos(ang + 0.42) * L, y1 - math.sin(ang + 0.42) * L)]
    d.line([x0, y0, bx, by], fill=(*INK, 190), width=w + 4)
    d.line([x0, y0, bx, by], fill=color, width=w)
    d.polygon(head, fill=color, outline=(*INK, 220))


def draw_scene(img, seats, unassigned, k, F, full=True):
    fill = Image.new('RGBA', img.size, (0, 0, 0, 0)); fd = ImageDraw.Draw(fill)
    for s in seats:
        c = COLOR[s['status']][0]; z = s['zone']
        fd.ellipse([(z[0] - z[2]) * k, (z[1] - z[3]) * k, (z[0] + z[2]) * k, (z[1] + z[3]) * k], fill=(*c, 30 if s['status'] == 'NORMAL' else 70))
    img.alpha_composite(fill)
    d = ImageDraw.Draw(img)
    for u in unassigned:
        d.rectangle([v * k for v in u], outline=(*GREY, 210), width=max(2, round(3 * k)))
        if full: chip(d, u[0] * k, u[1] * k, 'PERSON', F['small'], (71, 85, 105, 235))
    order = sorted(seats, key=lambda s: s['zone'][1])
    for s in order:                                   # desk zones and gaze lines first, so labels stay on top
        c = COLOR[s['status']][0]; z = s['zone']
        d.ellipse([(z[0] - z[2]) * k, (z[1] - z[3]) * k, (z[0] + z[2]) * k, (z[1] + z[3]) * k], outline=(*c, 215), width=max(2, round(3 * k)))
    for s in order:
        if s['gaze']:
            g = [v * k for v in s['gaze']]; c = COLOR[s['status']][0] if s['status'] != 'NORMAL' else AMBER
            arrow(d, g[0], g[1], g[2], g[3], (*c, 255), max(3, round(6 * k)))
    for s in order:
        c, cdk = COLOR[s['status']]; z = s['zone']; anchor = None
        if s['box'] is not None:
            b = [v * k for v in s['box']]; w = max(3, round((7 if s['flash'] else 4.5) * k))
            d.rectangle(b, outline=(*c, 255), width=w); anchor = b
            for x, y in s['hands']:
                r = max(3, 6 * k); d.ellipse([x * k - r, y * k - r, x * k + r, y * k + r], fill=(*SKY, 255), outline=(8, 47, 73, 255), width=max(1, round(2 * k)))
            for x, y in s['head']:
                r = max(2, 3.6 * k); d.ellipse([x * k - r, y * k - r, x * k + r, y * k + r], fill=(255, 255, 255, 255), outline=(15, 23, 42, 255), width=1)
        if s['phone'] is not None:
            b = [v * k for v in s['phone']]; g = 6 * k; b = [b[0] - g, b[1] - g, b[2] + g, b[3] + g]
            d.rectangle(b, outline=(217, 70, 239, 255), width=max(3, round(4 * k)))
            if full: chip(d, b[0], b[3] + F['small'].size + 14, 'PHONE', F['small'], (162, 28, 175, 245))
        if anchor is None: anchor = [(z[0] - z[2]) * k, (z[1] - z[3]) * k]
        near = z[2] >= NEAR_RX; quiet = s['status'] == 'NORMAL' and s['target'] in ('own', None) and s['phone'] is None
        if not full: text = 'S%d' % s['id'] if quiet else 'S%d · %d' % (s['id'], s['risk'])
        elif quiet: text = 'S%d · NORMAL' % s['id'] if near else 'S%d' % s['id']
        else: text = 'S%d · %s · RISK %d' % (s['id'], s['status'], s['risk'])
        f = F['label'] if near or not quiet else F['small']
        chip(d, anchor[0] - 2, max(f.size + 14, anchor[1]), text, f, (*cdk, 245), fg=(255, 255, 255) if s['status'] != 'REVIEW' else (33, 20, 0))
        if full and (near or not quiet):                # far seats that are simply writing get no second line
            t = note(s); f = F['note']; tw = d.textlength(t, font=f); x = min(max(6, z[0] * k - tw / 2 - 8), img.width - tw - 22); y = min((z[1] + z[3]) * k + 6, img.height - f.size - 16)
            chip(d, x, y, t, f, (*INK, 205), fg=(*mix(c, (255, 255, 255), .55), 255) if s['status'] != 'NORMAL' else (226, 232, 240, 255), pad=(8, 4), radius=5, anchor='lt')


def panel(img, t, seats, toasts, F, pos, tagline, phones):
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    w = 372; row = 34 if len(seats) <= 7 else 28; h = 104 + row * len(seats) + 96; A = 226
    x = 36 if pos[1] == 'l' else img.width - w - 36; y = 36 if pos[0] == 't' else img.height - h - 36
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=(*INK, A), outline=(70, 84, 102, A), width=2)
    crest(d, x + 38, y + 38, 15, (115, 229, 195, 255))
    d.text((x + 64, y + 38), 'SENTINEL VISION', font=F['brand'], fill=(240, 246, 250, 255), anchor='lm')
    d.ellipse([x + w - 78, y + 32, x + w - 66, y + 44], fill=RED + (255,) if int(t * 2) % 2 == 0 else mix(INK, RED, .35) + (255,))
    d.text((x + w - 58, y + 38), 'LIVE', font=F['tiny'], fill=(226, 232, 240, 255), anchor='lm')
    d.text((x + 24, y + 78), f'Exam hall  ·  t = {t:05.1f}s', font=F['sub'], fill=(148, 163, 184, 255), anchor='lm')
    yy = y + 104
    for s in seats:
        c = COLOR[s['status']][0]
        if s['flash']: d.rounded_rectangle([x + 12, yy - 1, x + w - 12, yy + row - 5], radius=9, fill=mix(INK, c, .28) + (A,))
        m = (row - 5) / 2
        d.ellipse([x + 24, yy + m - 8, x + 40, yy + m + 8], fill=c + (255,))
        d.text((x + 54, yy + m), 'S%d' % s['id'], font=F['row'], fill=(226, 232, 240, 255), anchor='lm')
        d.text((x + 102, yy + m), s['status'], font=F['rowb'], fill=c + (255,), anchor='lm')
        bx0, bx1 = x + 226, x + w - 70; d.rounded_rectangle([bx0, yy + m - 4, bx1, yy + m + 4], radius=4, fill=(51, 65, 85, 255))
        if s['risk'] > 0: d.rounded_rectangle([bx0, yy + m - 4, bx0 + max(8, (bx1 - bx0) * s['risk'] / 100), yy + m + 4], radius=4, fill=c + (255,))
        d.text((x + w - 24, yy + m), str(s['risk']), font=F['rowb'], fill=(226, 232, 240, 255), anchor='rm')
        yy += row
    d.line([x + 24, yy + 6, x + w - 24, yy + 6], fill=(70, 84, 102, 255), width=2)
    flags = sum(s['status'] == 'FLAGGED' for s in seats); present = sum(s['box'] is not None for s in seats)
    for label, value, color, lx in (('Seated', present, GREEN, 24), ('Phones', phones, (217, 70, 239) if phones else GREY, 142), ('Flags', flags, RED if flags else GREY, 264)):
        d.text((x + lx, yy + 34), label, font=F['sub'], fill=(203, 213, 225, 255), anchor='lm')
        d.text((x + lx + d.textlength(label, font=F['sub']) + 10, yy + 34), str(value), font=F['num'], fill=color + (255,), anchor='lm')
    d.text((x + 24, yy + 70), 'Flags are sent to a person for review', font=F['fine'], fill=(148, 163, 184, 255), anchor='lm')
    img.alpha_composite(layer)
    if toasts:
        e = toasts[-1]; age = t - e['t']; ease = min(1, age / .25); fade = min(1, (TOAST_SECONDS - age) / .35)
        text = 'S%d  ·  %s' % (e['id'], e['text']); c = COLOR[e['to']][0]; tag = {'NORMAL': 'CLEARED', 'REVIEW': 'REVIEW', 'FLAGGED': 'FLAGGED'}[e['to']]
        tl = Image.new('RGBA', img.size, (0, 0, 0, 0)); td = ImageDraw.Draw(tl)
        gw = td.textlength(tag, font=F['tiny']); tw = td.textlength(text, font=F['toast']); bw = tw + gw + 78
        bx = (img.width - bw) / 2 + (0 if pos[0] == 't' else (w / 2 + 18) * (1 if pos[1] == 'l' else -1)); by = img.height - 118 + (1 - ease) * 40
        td.rounded_rectangle([bx, by, bx + bw, by + 68], radius=16, fill=(*INK, 235), outline=c + (255,), width=3)
        td.text((bx + 26, by + 34), tag, font=F['tiny'], fill=c + (255,), anchor='lm')
        td.text((bx + 26 + gw + 22, by + 34), text, font=F['toast'], fill=(241, 245, 249, 255), anchor='lm')
        tl.putalpha(tl.getchannel('A').point(lambda v: int(v * fade * ease))); img.alpha_composite(tl)


def compose_vertical(frame_img, t, seats, unassigned, F, phones):
    W, H = 1080, 1920
    if not hasattr(compose_vertical, 'bg'):
        bg = Image.new('RGBA', (W, H), (*INK, 255)); bd = ImageDraw.Draw(bg)
        for yy in range(H):
            q = yy / H; bd.line([(0, yy), (W, yy)], fill=(int(9 + 7 * q), int(15 + 13 * q), int(22 + 16 * q), 255))
        compose_vertical.bg = bg
    canvas = compose_vertical.bg.copy(); d = ImageDraw.Draw(canvas)
    tw = d.textlength('SENTINEL VISION', font=F['v_brand']); left = (W - (tw + 92)) / 2
    crest(d, left + 32, 176, 32, (115, 229, 195, 255))
    d.text((left + 92, 176), 'SENTINEL VISION', font=F['v_brand'], fill=(240, 246, 250, 255), anchor='lm')
    d.text((W / 2, 256), 'Exam hall  ·  head direction, desk zones, phones', font=F['v_sub'], fill=(148, 163, 184, 255), anchor='mm')
    vy = 336; vh = round(W * frame_img.height / frame_img.width)
    video = frame_img.resize((W, vh), Image.LANCZOS).convert('RGBA')
    draw_scene(video, seats, unassigned, W / frame_img.width, F_V(F), full=False)
    canvas.alpha_composite(video, (0, vy))
    d.rectangle([0, vy - 3, W, vy], fill=(52, 66, 82, 255)); d.rectangle([0, vy + vh, W, vy + vh + 3], fill=(52, 66, 82, 255))
    d.ellipse([44, vy + vh + 40, 62, vy + vh + 58], fill=RED + (255,) if int(t * 2) % 2 == 0 else mix((14, 24, 34), RED, .35) + (255,))
    d.text((76, vy + vh + 49), f'LIVE  ·  t = {t:05.1f}s', font=F['v_small'], fill=(203, 213, 225, 255), anchor='lm')
    d.text((W - 44, vy + vh + 49), 'Flags go to a person for review', font=F['v_small'], fill=(148, 163, 184, 255), anchor='rm')
    rows = (len(seats) + 1) // 2; cy0 = vy + vh + 96; cw, gap = 478, 18; ch = min(124, int((1664 - cy0) / rows) - gap)
    for n, s in enumerate(seats):
        col, r = n % 2, n // 2; cx = 48 + col * (cw + gap); cy = cy0 + r * (ch + gap); c = COLOR[s['status']][0]
        d.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=22, fill=mix((14, 24, 34), c, .34 if s['flash'] else .13) + (255,), outline=c + (255,), width=5 if s['flash'] else 3)
        d.text((cx + 26, cy + ch * .33), 'S%d' % s['id'], font=F['v_id'], fill=(226, 232, 240, 255), anchor='lm')
        d.text((cx + 112, cy + ch * .33), s['status'], font=F['v_status'], fill=(*c, 255), anchor='lm')
        d.text((cx + cw - 26, cy + ch * .33), str(s['risk']), font=F['v_status'], fill=(241, 245, 249, 255), anchor='rm')
        d.text((cx + 26, cy + ch * .75), note(s), font=F['v_note'], fill=(148, 163, 184, 255), anchor='lm')
    by = cy0 + rows * (ch + gap) + 22
    flags = sum(s['status'] == 'FLAGGED' for s in seats); present = sum(s['box'] is not None for s in seats)
    for label, value, color, bx in (('SEATED', present, GREEN, W * .2), ('PHONES', phones, (217, 70, 239) if phones else GREY, W * .5), ('FLAGS', flags, RED if flags else GREY, W * .8)):
        d.text((bx, by + 46), str(value), font=F['v_num'], fill=(*color, 255), anchor='mm')
        d.text((bx, by + 118), label, font=F['v_cap'], fill=(148, 163, 184, 255), anchor='mm')
    return canvas


def F_V(F): return {'label': F['v_label'], 'small': F['v_small2'], 'note': F['v_small2']}


def fonts():
    return {'brand': font('ExtraBold', 22), 'tiny': font('Bold', 15), 'sub': font('Medium', 17), 'row': font('SemiBold', 19), 'rowb': font('Bold', 19),
            'num': font('ExtraBold', 25), 'toast': font('SemiBold', 26), 'label': font('Bold', 21), 'small': font('Bold', 17), 'note': font('SemiBold', 17), 'fine': font('Medium', 15),
            'v_brand': font('ExtraBold', 58), 'v_sub': font('Medium', 27), 'v_label': font('Bold', 21), 'v_small': font('SemiBold', 24), 'v_small2': font('Bold', 16),
            'v_id': font('SemiBold', 32), 'v_status': font('ExtraBold', 33), 'v_note': font('Medium', 23), 'v_num': font('ExtraBold', 88), 'v_cap': font('Bold', 26)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video'); ap.add_argument('states'); ap.add_argument('out')
    ap.add_argument('--layout', choices=['landscape', 'vertical'], default='landscape')
    ap.add_argument('--crf', type=int, default=19); ap.add_argument('--still', type=float)
    a = ap.parse_args()
    S = json.load(open(a.states)); scene = Scene(S); cap = cv2.VideoCapture(a.video); fps = S['fps']
    F = fonts()
    size = (S['width'], S['height']) if a.layout == 'landscape' else (1080, 1920); proc = None
    if a.still is None:
        proc = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{size[0]}x{size[1]}', '-r', str(fps), '-i', '-', '-an',
                                 '-c:v', 'libx264', '-crf', str(a.crf), '-preset', 'slow', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', a.out], stdin=subprocess.PIPE)
    n = len(S['frames'])
    for i in range(n):
        ok, bgr = cap.read()
        if not ok: break
        t, seats, unassigned, toasts = scene.frame(i); phones = S['frames'][i]['phones']
        if a.still is not None and t < a.still: continue
        base = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        if a.layout == 'landscape':
            img = base.convert('RGBA'); draw_scene(img, seats, unassigned, 1.0, F); panel(img, t, seats, toasts, F, S.get('panel', 'tl'), S.get('tagline', ''), phones)
        else: img = compose_vertical(base, t, seats, unassigned, F, phones)
        if a.still is not None: img.convert('RGB').save(a.out); print('still at', t); return
        proc.stdin.write(img.convert('RGB').tobytes())
    proc.stdin.close(); proc.wait(); print('wrote', a.out, n, 'frames')


if __name__ == '__main__':
    main()
