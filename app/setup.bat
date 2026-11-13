@echo off
rem Creates a private Python environment in .venv and installs what the apps need. Safe to run again.
cd /d "%~dp0"
if exist .venv\.ready exit /b 0

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Python 3 was not found.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then run this again.
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  echo Creating a private Python environment in .venv ...
  %PY% -m venv .venv || exit /b 1
)
call .venv\Scripts\activate.bat || exit /b 1
python -m pip install --upgrade pip >nul
echo Installing OpenCV, NumPy and Pillow ...
pip install "opencv-python>=4.9" "numpy>=1.26" "pillow>=10" || exit /b 1
echo Installing ONNX Runtime with DirectML, which uses any DirectX 12 graphics card ...
pip install onnxruntime-directml
if errorlevel 1 (
  echo DirectML build not available for this Python. Installing the CPU build instead.
  pip install onnxruntime || exit /b 1
)
echo ok> .venv\.ready
exit /b 0
