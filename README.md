# Sentinel Vision

Camera analytics that turns footage into timestamped statuses: who is at their desk, which zone is over its limit, who is at the front door, whose head has turned toward another desk in an exam.

This repository holds the public site, the pipeline that produced the four demo clips shown on it, four live apps that run the same rules on a webcam or any video, and the tests.

Live site: https://sentinel-vision-demo.netlify.app

Windows build: https://github.com/forgehk/sentinel-vision/releases/latest

[![Release](https://github.com/forgehk/sentinel-vision/actions/workflows/release.yml/badge.svg)](https://github.com/forgehk/sentinel-vision/actions/workflows/release.yml)

## Contents

| Path | What it is |
|---|---|
| `site/` | The static site as deployed. HTML, CSS, three JavaScript files, the videos, the ONNX models and the per-frame detection data. |
| `site-src/` | Source for the 3D scenes (`scene3d.js`, three.js). Bundled into `site/scene3d.js`. |
| `app/` | The live apps: one launcher per demo, the ONNX models, raw sample clips and the Windows build scripts. See `app/README.md`. |
| `pipeline/` | Python scripts that take a clip to an annotated video: detection, rules, rendering. The live apps import their rules and drawing code from here. |
| `pipeline/scenes/` | Zone and layout files for the shop-floor, front-yard and exam-hall clips. |
| `pipeline/tests/` | 41 unit tests for the rules. |
| `tools/serve_local.py` | Local web server for the site, with the headers the in-browser models need. |

## The four demos

| Clip | Models | Rules | Events in the clip |
|---|---|---|---|
| Office | YOLO26-L, 1280 px | Seat absence, phone in hand | ID 1 absent at 4.79 s. ID 6 phone at 7.04 s. ID 4 phone at 8.46 s. |
| Shop floor | YOLO26-L, 1280 px | Zone entry, dwell, occupancy | Stockroom door entered at 3.83 s. Aisle 1 dwell over 5 s at 5.00 s. Door cleared at 7.83 s. Checkout queue 4 of 3 at 8.21 s. |
| Front yard | YOLO26-L, 960 px | Zone entry by object type | Vehicle in the driveway at 3.46 s. Pet on the lawn at 3.46 s, no alert. Person on the front path at 6.50 s. |
| Exam hall | YOLO26-L pose and YOLO26-L, 1280 px | Head turn, gaze target, phone at desk, risk score | S8 under review at 2.00 s and flagged at 2.83 s, looking at desk S9. S9 flagged at 4.71 s, phone at the desk. |

Each clip is 241 frames at 24 fps. Across the four, the models produced 7,068 detections above 25% confidence and 41,801 body keypoints, and the rules logged 13 status changes.

The footage is generated video (Seedance 2.5). Nobody in it is a real person, and the site says the scenes are simulated. Everything drawn over the footage is model output passed through the rules below. No box, label or event is keyed by hand.

## How a clip is produced

```bash
cd pipeline
pip install ultralytics opencv-python pillow        # plus ffmpeg and the Inter font

./grade.sh clip.mp4 clip_graded.mp4                  # camera-feed look; no geometry change

# office
python detect.py clip_graded.mp4 detections.json --classes 0,67
python analyze.py detections.json states.json
python render.py clip_graded.mp4 states.json out_16x9.mp4 --layout landscape

# shop floor (people only) and front yard (people, vehicles, pets)
python detect.py clip_graded.mp4 detections.json --classes 0
python detect.py clip_graded.mp4 detections.json --classes 0,2,5,7,15,16,24 --imgsz 960
python zones_analyze.py detections.json scenes/shop.json states.json
python render_zones.py clip_graded.mp4 states.json out_16x9.mp4 --layout landscape

# exam hall
python detect_pose.py clip_graded.mp4 detections.json
python exam_analyze.py detections.json states.json scenes/exam.json
python render_exam.py clip_graded.mp4 states.json out_16x9.mp4 --layout landscape
```

Every renderer also takes `--layout vertical` for a 1080×1920 version and `--still 5.2` to write one frame as a PNG.

`detections.json` is the raw model output. `states.json` is what the rules made of it. The renderers read only `states.json`, so a change to a threshold shows up in the video without running the models again.

## Live apps

`app/` holds four programs: Office, Shop, Home and Exam. Each opens a window, plays a raw sample clip and annotates it as it plays with the ONNX models in `app/models/`. One key switches to a webcam, another opens any video file.

Each release carries a Windows build: one folder with four EXEs, the models and the sample clips. `.github/workflows/release.yml` produces it. On every push it runs the rule tests, builds the folder on a Windows machine, starts each EXE on its sample clip and fails unless the expected events are reported. On `main`, when the version number in `app/sentinel_live.py` has no release yet, the same run publishes the zip and its SHA-256 as that release. `app/build_exe.bat` does the same build on your own PC.

The live apps and the offline pipeline share one set of rules. `OfficeRules`, `ZoneRules` and `ExamRules` each take one frame of detections and the time since the last one. The batch scripts call them at the clip's frame rate. The apps call them at whatever rate the machine manages. After the rules were moved into these classes, all four demo clips were re-analysed and the output matched the earlier files exactly.

`app/README.md` has the keys, the build steps, measured speeds and a short script for demonstrating the apps to an audience.

## Rules

Thresholds are constants at the top of each script.

### Office (`analyze.py`)

Seats are learned from the first second of the clip. Each person who stays put becomes a seat, numbered back to front and left to right.

| Status | Rule |
|---|---|
| WORKING | A person is detected in the seat and no phone is detected in their hands. It means the person is at the desk. |
| ABSENT | No person in the seat for 0.75 s. Clears after 0.4 s back. |
| PHONE USAGE | A phone box sits inside the person's box, away from where phones were lying during the first second, for 0.35 s. |

### Zones (`zones_analyze.py`)

A scene file lists polygons in image coordinates, each with one rule.

| Kind | Fires when |
|---|---|
| `entry` | An object of the zone's target type (person, vehicle or pet) is inside for `seconds`. The status stays up for `latch` seconds after the zone empties. |
| `dwell` | The same tracked person has been inside for `seconds`. |
| `occupancy` | More than `limit` people are inside for `hold` seconds. |

Each zone has a level (`alert`, `notice`, `info`), so a car in the driveway is logged without raising an alarm and a dog on the lawn is recognised and ignored.

### Exam hall (`exam_analyze.py`)

The pose model returns 17 keypoints per person. The rules use nine of them: nose, eyes, ears, shoulders and wrists.

1. During the first second, each seated person becomes a seat. Their desk zone is an ellipse around where their wrists rest. Their baseline head direction is the median direction over that second.
2. Head direction is the vector from the midpoint of the ears to the nose, in the image plane. Yaw is how far that vector has rotated from the candidate's own baseline, in degrees.
3. A look leaves the candidate's own paper once yaw passes 38°. The target is then the desk zone the head points at. Each desk within 30° of the head direction and within seven shoulder-widths gets a cost (angular error plus distance, each as a fraction of its limit) and the lowest cost wins. The current target is kept unless another desk beats it by 0.25, which stops the label switching between two desks that sit almost in line.
4. A phone counts when a phone box is inside the candidate's box or desk zone for 0.35 s.

The risk score runs from 0 to 100 per seat.

| Constant | Value | Meaning |
|---|---|---|
| `LOOK_HOLD` | 0.35 s | A look must last this long before it scores |
| `LOOK_RATE` | 42 per second | Added while the head points at another desk |
| `DECAY_RATE` | 7 per second | Removed the rest of the time |
| `PHONE_RISK` | 85 | A phone at the desk lifts the score to at least this |
| `REVIEW_AT` | 25 | NORMAL becomes REVIEW |
| `FLAG_AT` | 60 | REVIEW becomes FLAGGED |

Looking up, or away at nothing, scores nothing. Only a look at another desk does.

A flag is a prompt for an invigilator to check the footage at that timestamp. The system makes no finding about what the candidate was doing.

## The site

The site is static. There is no framework and no server code. The contact form is a Netlify form.

```bash
pip install rangehttpserver
python3 tools/serve_local.py site 8765      # then open http://127.0.0.1:8765
```

Use this server instead of `python -m http.server`. It answers range requests, which video seeking needs, and it sends the `Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy` headers that let ONNX Runtime run on more than one thread. `site/_headers` sets the same headers on Netlify.

What the page does:

- Plays the four clips with an event log, and a raw-output view that lists the detections for the frame on screen, read from `site/data/*.json`.
- Runs YOLO26n (9.9 MB) or YOLO26n-pose (12.1 MB) in the visitor's browser with ONNX Runtime Web, on a sample frame, a photo they choose or their own camera. On the camera it runs every frame and applies the desk rule or the head-direction readout to the person in view. The picture is read from a canvas and passed to WebAssembly. Nothing is uploaded.
- Offers the Windows build, with its size and SHA-256, and lists the four model files with their checksums. `site/docs/` is the documentation page.
- Shows five floor models (office, shop, exam hall, plant, home) on a turntable that turns with the scroll, and a ceiling camera in the header that follows the pointer. Both are built from three.js primitives, so there are no model files to download.
- Falls back to plain content without WebGL, and holds still when the visitor's system asks for reduced motion.

To rebuild the 3D bundle after editing `site-src/scene3d.js`:

```bash
cd site-src
npm install
npm run build
```

To deploy, publish the `site/` folder. `site/netlify.toml` sets the publish directory.

## Measured performance

All figures are from a 2-core 2.1 GHz Xeon cloud machine with no GPU.

| Model | Input | Time per frame |
|---|---|---|
| YOLO26n, ONNX Runtime | 640 px | 68 ms |
| YOLO26s, ONNX Runtime | 640 px | 208 ms |
| YOLO26-L, PyTorch | 1280 px | about 2 s |
| YOLO26-L pose and YOLO26-L together | 1280 px | 4.0 s (241 frames in 970 s) |
| YOLO26n in Chrome, WebAssembly, 2 threads | 640 px | about 200 ms |
| YOLO26n-pose in Chrome, WebAssembly, 2 threads | 640 px | about 200 ms |

The demo clips were analysed offline with the large models. The nano models on the site load quickly and find fewer small objects: on the exam-hall sample frame the nano pose model finds five of the ten candidates.

## Tests

```bash
cd pipeline
python -m unittest discover -s tests
```

41 tests. They build synthetic detections, run the rules and check the events: a seat emptying, a phone in hand against a phone resting on the desk, zone entry and its latch, a dwell timer surviving a tracker ID switch, a queue at and over its limit, a head turning toward the next desk, the choice between two desks in line, score decay, and a phone at a desk. Seven feed the rules one frame at a time, as the live apps do. Two of those repeat a scenario at 24, 12 and 8 frames a second and check that the event fires at the same moment.

`app/tests/` has eight more for the live apps.

## Roadmap

Version 0.1.0 has the four programs, webcam and video-file input, zones you draw, a CSV event log and annotated video. In development:

- A review screen: jump to an event, mark it checked, add a note
- Movement heatmaps
- IP cameras over RTSP
- A retention timer for logs and clips
- One program with an installer

## Licences

- This repository is released under the GNU Affero General Public License v3.0. See `LICENSE`.
- The YOLO26 weights are from Ultralytics and are AGPL-3.0, which is why the rest is too. Closed-source commercial use needs an Ultralytics Enterprise licence. The site serves two of the weight files, and `app/models/` holds four.
- ONNX Runtime Web and three.js are MIT.
- Archivo (site) and Inter (video overlays) are under the SIL Open Font License.

## Limits

- Head direction is measured in the image plane from one camera. It is a good signal for a head turned sideways and a weak one for a head tilted toward or away from the camera. When the nose is hidden, as in a view from behind, no direction is reported.
- The gaze target is the best-aligned nearby desk. It is not a measurement of what the eyes are on.
- Phones are small. The large model at 1280 px finds a phone held on a desk a few metres away. The nano model usually does not.
- Seats are learned from the first second. Someone who sits down later is reported as a person, without a seat.
- The clips are ten seconds long and generated. They show that the pipeline runs end to end. They are not an accuracy benchmark.

## Responsible use

A status is an observation. "Working" means someone is at their desk. "Flagged" means a head stayed turned toward another desk, or a phone appeared. Neither says why. Review the footage before acting on any of it, tell the people in frame that the system is running and what it records, and follow the monitoring and privacy rules that apply where you operate.
