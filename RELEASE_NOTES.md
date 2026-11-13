First public build.

`SentinelVision-windows-x64.zip` holds four programs for Windows 10 and 11 (64-bit): `SentinelOffice.exe`, `SentinelShop.exe`, `SentinelHome.exe` and `SentinelExam.exe`. Unzip it anywhere and double-click one. Each plays a raw sample clip and annotates it live with the ONNX models in the `models` folder. W switches to a webcam and O opens any video. `README.md` inside the folder lists the keys.

The programs are not code-signed, so Windows may ask before the first run. Choose "More info", then "Run anyway".

This build was made by the Release workflow in this repository. Before publishing, the workflow started each of the four programs on its sample clip on a Windows machine and checked that it reported the expected events. That machine has no camera and no graphics card, so webcam input and GPU inference are not part of the check.

`SHA256SUMS.txt` has the checksum of the zip.
