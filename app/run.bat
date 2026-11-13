@echo off
rem Runs one of the live apps from source, without building an EXE.
rem   run.bat office          run.bat exam --source 0          run.bat shop --source my_clip.mp4
cd /d "%~dp0"
call setup.bat
if errorlevel 1 ( pause & exit /b 1 )
set "MODE=%~1"
if "%MODE%"=="" set "MODE=office"
shift
.venv\Scripts\python.exe sentinel_live.py %MODE% %1 %2 %3 %4 %5 %6
if errorlevel 1 pause
