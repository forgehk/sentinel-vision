"""Run YOLO26 pose (people + 17 body keypoints, tracked) and YOLO26 detection (phones) over a clip.

    python detect_pose.py clip.mp4 detections.json [--pose yolo26l-pose.pt] [--det yolo26l.pt] [--imgsz 1280]

Output, per frame:
    people: [conf, x1, y1, x2, y2, track_id, [x, y, conf] * 17]     COCO keypoint order
    phones: [conf, x1, y1, x2, y2]
Nothing here is scripted: every box and keypoint in the output came from the models.
"""
import argparse, json, time
import cv2
from ultralytics import YOLO

ap = argparse.ArgumentParser()
ap.add_argument('video'); ap.add_argument('out')
ap.add_argument('--pose', default='yolo26l-pose.pt'); ap.add_argument('--det', default='yolo26l.pt')
ap.add_argument('--imgsz', type=int, default=1280)
ap.add_argument('--conf', type=float, default=0.25); ap.add_argument('--phone-conf', type=float, default=0.08)
ap.add_argument('--max-frames', type=int, default=0)
a = ap.parse_args()

pose = YOLO(a.pose); det = YOLO(a.det)
cap = cv2.VideoCapture(a.video)
fps = cap.get(cv2.CAP_PROP_FPS); w = int(cap.get(3)); h = int(cap.get(4)); n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
frames = []; t0 = time.time()
while True:
    ok, frame = cap.read()
    if not ok or (a.max_frames and len(frames) >= a.max_frames): break
    r = pose.track(frame, persist=True, imgsz=a.imgsz, conf=a.conf, tracker='bytetrack.yaml', verbose=False)[0]
    people = []
    kp = r.keypoints.data.tolist() if r.keypoints is not None else []
    for b, k in zip(r.boxes, kp):
        tid = int(b.id) if b.id is not None else -1
        people.append([round(float(b.conf), 3), *[round(float(v), 1) for v in b.xyxy[0].tolist()], tid,
                       [[round(x, 1), round(y, 1), round(c, 2)] for x, y, c in k]])
    p = det.predict(frame, imgsz=a.imgsz, conf=a.phone_conf, classes=[67], verbose=False)[0]
    phones = [[round(float(b.conf), 3), *[round(float(v), 1) for v in b.xyxy[0].tolist()]] for b in p.boxes]
    frames.append({'people': people, 'phones': phones})
    if len(frames) % 20 == 0: print(f'{len(frames)}/{n} frames, {time.time()-t0:.0f}s', flush=True)
json.dump({'video': a.video, 'pose_model': a.pose, 'det_model': a.det, 'imgsz': a.imgsz, 'fps': fps, 'width': w, 'height': h, 'frames': frames}, open(a.out, 'w'))
print('done', len(frames), 'frames in %.0fs' % (time.time() - t0))
