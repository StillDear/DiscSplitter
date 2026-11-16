@echo off
REM Builds the Windows installer (dist\DiscSplitter_<date>_Windows_x64_Setup.exe), with ffmpeg/ffprobe
REM and mkvmerge/mkvextract bundled. See packaging\build_installer.py for the options.
REM Needs: python -m pip install -r requirements-dev.txt, and Inno Setup 6.

cd /d "%~dp0.."
set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe

%PY% packaging\build_installer.py %*
if %ERRORLEVEL% NEQ 0 (
    pause
    exit /b %ERRORLEVEL%
)
pause
