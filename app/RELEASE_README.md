# Sentinel Vision for Windows

Four programs: `SentinelOffice.exe`, `SentinelShop.exe`, `SentinelHome.exe` and `SentinelExam.exe`. Double-click one. It plays a raw sample clip and annotates it as it plays, using the ONNX models in `models/`. Nothing in the picture is pre-rendered and nothing leaves this PC.

Windows may warn the first time, because the programs are not code-signed. Choose "More info", then "Run anyway".

Keep everything in this folder together. The programs read `models`, `samples`, `zones` and `fonts` at start, and share the `_internal` folder.

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
| X | Save a screenshot to `logs`. |
| Q | Quit. |

The box in the bottom corner shows the model, its input size, whether it is running on the GPU or the CPU, the time the last frame took, the frame rate and the number of detections.

Every status change is written to a CSV in `logs`.

## Things to try

1. Press W. In Office, sit still for a second so your seat is mapped, then pick up your phone, then walk away.
2. In Exam, turn your head and watch the yaw figure. Hold a phone over the desk.
3. In Shop or Home, press Z, click a zone around a doorway, pick a rule and walk into it.
4. Press O and open any video.
5. Disconnect from the network. Nothing changes.

## If something goes wrong

A program that cannot start writes the reason to `sentinel.log` in this folder. If the graphics card cannot be used, the program runs on the CPU and says so in the corner box.

Source code, tests and the build that produced this folder: https://github.com/forgehk/sentinel-vision

The YOLO26 models are from Ultralytics and are licensed AGPL-3.0, as is this software. See `LICENSE.txt`.
