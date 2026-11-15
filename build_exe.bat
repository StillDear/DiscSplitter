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
REM compiled from engine\ first when needed), but NOT mkvmerge/mkvextract/
REM ffmpeg/ffprobe - those still need to be installed separately and
REM reachable on PATH (or located in the app's Settings > External tools).

if not exist "engine\bin\tsMuxeR.exe" python engine\build_engine.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Engine build FAILED - see the error above.
    pause
    exit /b %ERRORLEVEL%
)

set DISCSPLITTER_ONEFILE=1
python -m PyInstaller --noconfirm packaging\installer.spec

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Build FAILED - see the error above.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Build finished. Exe is in the "dist" folder.
pause
