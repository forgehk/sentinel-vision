# Sentinel Vision live apps

Four programs, one per demo: Office, Shop, Home and Exam. Each opens a window, plays a raw sample clip and annotates it as it plays, using the ONNX models in `models/`. Press W to switch to your webcam or O to open any video.

Nothing in the picture is pre-rendered. The sample clips in `samples/` have no overlay in them. The boxes, keypoints, statuses and alerts are computed frame by frame on your machine, by the same rule classes the offline pipeline uses (`../pipeline`).

## What is in this folder

| Path | What it is |
|---|---|
| `SentinelOffice.py`, `SentinelShop.py`, `SentinelHome.py`, `SentinelExam.py` | The four launchers. Each becomes one EXE. |
| `sentinel_live.py` | The program itself: model loading, tracking, the window, the keys. |
| `models/` | `yolo26n.onnx`, `yolo26s.onnx` (objects) and `yolo26n-pose.onnx`, `yolo26s-pose.onnx` (people with 17 body keypoints). |
| `samples/` | One raw clip per demo, with nothing drawn on it. |
| `zones/` | Zone files for the shop and front-yard sample clips. Zones you draw for your own camera are saved here too. |
| `fonts/`, `assets/` | The Inter typeface for the overlay, and the program icon. |
| `build_exe.bat`, `run.bat`, `setup.bat` | Windows scripts: build the EXEs, run from source, install what is needed. |
| `sentinel.spec` | The PyInstaller recipe: four programs sharing one runtime folder. |
| `RELEASE_README.md` | The short guide that ships inside the Windows build. |
| `tests/` | Tests for the tracker, plus short runs of each app on its sample clip. |
| `logs/` | Created on first use. One CSV of events per session, and any screenshots you take. |

## Get the Windows build

A ready-made build is attached to each release at https://github.com/forgehk/sentinel-vision/releases. It is produced on GitHub's Windows machines, which also start each of the four programs on its sample clip and check the result before the release is published.

## Build it yourself (Windows)

1. Install Python 3.10 or newer from python.org and tick "Add python.exe to PATH".
2. Double-click `build_exe.bat`.

The first run takes a few minutes. It creates a private Python environment in `.venv`, installs ONNX Runtime, OpenCV, Pillow and PyInstaller into it, and builds `dist\SentinelVision`. That folder holds `SentinelOffice.exe`, `SentinelShop.exe`, `SentinelHome.exe` and `SentinelExam.exe`, one shared copy of Python, OpenCV and ONNX Runtime in `_internal`, and copies of `models`, `samples`, `zones` and `fonts`.

Keep the folder together. To use it on another PC, copy the whole folder. That PC does not need Python.

Windows may warn the first time an EXE runs, because it is not code-signed. Choose "More info", then "Run anyway".

To run without building, use `run.bat office`, `run.bat shop`, `run.bat home` or `run.bat exam`.

## Keys

| Key | Does |
|---|---|
| W | Webcam. Press again for the next camera. |
| O | Open a video file. |
| S | Back to the sample clip. |
| M | Switch between the small model and the nano model. |
| [ and ] | Smaller or larger model input: 640, 960 or 1280 pixels. |
| R | Start again: seats are mapped afresh and timers go to zero. |
| Z | Draw a zone (Shop and Home). Click each corner, press Enter, then pick the rule with a number key. |
| C | Clear all zones (Shop and Home). |
| P | Pause. |
| H | Show or hide the key hints. |
| F | Full screen. |
| X | Save a screenshot to `logs/`. |
| Q | Quit. |

The box in the bottom corner shows what is running: the model, its input size, whether it is on the GPU or the CPU, the inference time for the last frame, the frame rate and the number of detections.

## Showing that it is real

1. Start an app. The sample clip plays with no overlay in the file, and the overlay appears on top. The readout in the corner shows the model and the time each frame took.
2. Press W. In Office, sit still for a second so your seat is mapped. Pick up your phone: the status changes to PHONE USAGE in about half a second. Walk out of frame: ABSENT.
3. In Exam, turn your head and the yaw figure follows it. With two people in view, turn toward the other person's desk: REVIEW, then FLAGGED. Hold a phone over your desk: FLAGGED.
4. In Shop or Home, press Z, click a zone around a doorway and choose a rule. Walk into it.
5. Press O and open a clip someone in the room gives you.
6. Press M, then [ and ]. The inference time changes with the model and the input size, because the work is being done as you watch.
7. Unplug the network. Nothing changes: the models are files in `models/` and run locally.
8. Open `logs/`. Every status change is in a CSV with its time.

## Speed and accuracy

Inference time per frame on a 2-core 2.1 GHz Xeon with no GPU:

| Model and input | Office, Shop, Home | Exam (pose and objects) |
|---|---|---|
| nano, 640 px | 40 to 57 ms | 94 ms |
| nano, 1280 px | 165 to 173 ms | 380 ms |
| small, 640 px | 119 to 158 ms | 256 ms |
| small, 1280 px | 463 to 553 ms | 1,037 ms |

On Windows the apps use the DirectML build of ONNX Runtime, which runs on any DirectX 12 graphics card. That path has not been timed here. If the GPU cannot be used, the app falls back to the CPU and says so in the readout.

The app picks its own defaults: the small model at 1280 px for a video file on a GPU, and 640 px on a CPU or for a webcam, where people are close to the camera.

What each setting finds on the sample clips:

- Small at 1280 px finds every event the demo videos show: the empty seat and both phones in the office, all four shop events, the car, dog and person at the house, and both exam flags.
- Nano at 640 px finds the empty seat but not the phones, all the shop and front-yard events with the queue alert flickering, and the exam head turn but not the phone.

When the machine cannot keep up with a file, frames are dropped so the clip stays at real speed. The rules run on clip time, so events fire at the same moments either way.

## Limits

- A single person on a webcam cannot be flagged for looking at another desk, because there is no other desk. The yaw figure still moves, and a phone still flags.
- The smaller pose model places head keypoints less steadily than the large one used for the demo videos, so its gaze target is occasionally wrong.
- Zones you draw use the centre of each detected box, since feet are rarely in view on a webcam.
- The release check runs each program on its sample clip on a Windows machine with no camera and no graphics card. The webcam, the file picker and GPU inference are not covered by it.

## Tests

```bash
python -m unittest discover -s tests
```

Eight tests. Four cover the tracker. Four start an app on its sample clip with the nano model and check the result: the front yard reports the vehicle, the pet and the person; the office maps its seats and sees one empty; a zone drawn with scripted mouse clicks is added and fires; the exam app maps seats with the pose model.

## Licence

The YOLO26 weights in `models/` are from Ultralytics and are AGPL-3.0. Closed-source commercial use needs an Ultralytics Enterprise licence. An EXE built from this folder and shipped with those weights is covered by the same terms.
