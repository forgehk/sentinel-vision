"""Run YOLO26 detection with tracking over a clip; save raw per-frame detections.

    python detect.py clip.mp4 detections.json [--model yolo26l.pt] [--imgsz 1280]

Nothing here is scripted: every box in the output came from the model.
"""
import argparse, json, time
import cv2
from ultralytics import YOLO

ap = argparse.ArgumentParser()
ap.add_argument('video'); ap.add_argument('out')
ap.add_argument('--model', default='yolo26l.pt'); ap.add_argument('--imgsz', type=int, default=1280)
ap.add_argument('--conf', type=float, default=0.08)
ap.add_argument('--classes', default='0,67', help='COCO class ids to keep, comma separated')
a = ap.parse_args()

CLASSES = [int(c) for c in a.classes.split(',')]
model = YOLO(a.model)
cap = cv2.VideoCapture(a.video)
fps = cap.get(cv2.CAP_PROP_FPS); w = int(cap.get(3)); h = int(cap.get(4)); n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
frames = []; t0 = time.time()
while True:
    ok, frame = cap.read()
    if not ok: break
    r = model.track(frame, persist=True, imgsz=a.imgsz, conf=a.conf, classes=CLASSES, tracker='bytetrack.yaml', verbose=False)[0]
    dets = []
    for b in r.boxes:
        tid = int(b.id) if b.id is not None else -1
        dets.append([int(b.cls), round(float(b.conf), 3), *[round(float(v), 1) for v in b.xyxy[0].tolist()], tid])
    frames.append(dets)
    if len(frames) % 20 == 0: print(f'{len(frames)}/{n} frames, {time.time()-t0:.0f}s', flush=True)
json.dump({'video': a.video, 'model': a.model, 'imgsz': a.imgsz, 'fps': fps, 'width': w, 'height': h, 'frames': frames}, open(a.out, 'w'))
print('done', len(frames), 'frames in %.0fs' % (time.time() - t0))
