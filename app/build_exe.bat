@echo off
rem Builds dist\SentinelVision: SentinelOffice.exe, SentinelShop.exe, SentinelHome.exe and SentinelExam.exe
rem sharing one copy of Python, OpenCV and ONNX Runtime, with the models, samples, zones and fonts beside them.
setlocal
cd /d "%~dp0"
title Sentinel Vision build
call setup.bat
if errorlevel 1 goto :fail
call .venv\Scripts\activate.bat
pip install pyinstaller || goto :fail

pyinstaller --noconfirm --clean sentinel.spec || goto :fail
for %%D in (models samples zones fonts) do robocopy "%%D" "dist\SentinelVision\%%D" /E /NFL /NDL /NJH /NJS /NP >nul
copy /y RELEASE_README.md dist\SentinelVision\README.md >nul

echo.
echo Done. Open dist\SentinelVision and double-click one of the four EXEs.
echo To use it on another PC, copy the whole SentinelVision folder. That PC does not need Python.
pause
exit /b 0

:fail
echo.
echo The build stopped. The first error above says why.
pause
exit /b 1
