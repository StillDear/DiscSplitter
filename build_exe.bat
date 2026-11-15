@echo off
REM Builds a standalone DiscSplitter.exe with PyInstaller.
REM --windowed means no console window is attached, so closing the
REM PowerShell/cmd window you launched it from can no longer kill the app.
REM
REM Uses "python -m PyInstaller" rather than the bare "pyinstaller" command,
REM since pip can install the package without its Scripts folder ending up
REM on PATH - calling it as a module always works.
REM
REM Needs the build tools first: python -m pip install -r requirements-dev.txt
REM
REM NOTE: this bundles the Python app and its built-in Blu-ray engine (tsMuxeR,
REM rebuilt from engine\ first when its source changed), but NOT mkvmerge/mkvextract/
REM ffmpeg/ffprobe - those still need to be installed separately and
REM reachable on PATH (or located in the app's Settings > External tools).

cd /d "%~dp0"
set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe

REM Incremental: quick when the engine is up to date, rebuilds it when its source changed.
%PY% engine\build_engine.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Engine build FAILED - see the error above.
    pause
    exit /b %ERRORLEVEL%
)

set DISCSPLITTER_ONEFILE=1
%PY% -m PyInstaller --noconfirm packaging\installer.spec

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Build FAILED - see the error above.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Build finished. Exe is in the "dist" folder.
pause
