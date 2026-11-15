# -*- mode: python ; coding: utf-8 -*-
# The one PyInstaller recipe for both builds:
#   folder build   packaging/build_installer.py runs this and packs the folder into the setup wizard
#   single file    build_exe.bat sets DISCSPLITTER_ONEFILE=1 for a portable DiscSplitter.exe
import os

ROOT = os.path.dirname(SPECPATH)
ONEFILE = os.environ.get('DISCSPLITTER_ONEFILE') == '1'
ICON = os.path.join(ROOT, 'disc_splitter.ico')

# The built-in Blu-ray engine (python engine/build_engine.py), unpacked to tools/ beside the app's own files.
ENGINE = os.path.join(ROOT, 'engine', 'bin', 'tsMuxeR.exe')
if not os.path.isfile(ENGINE):
    raise SystemExit('The Blu-ray engine is not built: run python engine/build_engine.py first')

a = Analysis(
    [os.path.join(ROOT, 'app.py')],
    pathex=[ROOT],
    binaries=[(ENGINE, 'tools')],
    datas=[(os.path.join(ROOT, 'qml'), 'qml'), (ICON, '.')],
    hiddenimports=['PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickControls2', 'PySide6.QtWidgets',
                   'PySide6.QtMultimedia'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'tkinter'],
    noarchive=False,
    optimize=0,
)

# PySide6's hook bundles every QML module; the app only uses QtQuick (Controls/Basic, Layouts,
# Dialogs) and QtMultimedia. Dropping the rest (WebEngine alone is ~200 MB) halves the build.
# The frozen app's --smoke-test loads every screen and dialog, so a needed module going missing shows up there.
UNUSED_QT = ('WebEngine', 'WebView', 'WebChannel', 'WebSockets', 'Qt3D', 'Qt63D', 'Quick3D', 'Charts',
             'DataVisualization', 'Graphs', 'Location', 'Positioning', 'RemoteObjects', 'Scxml', 'Sensors',
             'QtTest', 'Qt6Test', 'TextToSpeech', 'Qt5Compat', 'Core5Compat', 'ShaderTools', 'Pdf',
             'VirtualKeyboard', 'Material', 'Universal', 'Imagine', 'FluentWinUI3', 'qtwebengine')


def used(entry):
    parts = entry[0].replace('\\', '/').split('/')
    if not parts or parts[0] != 'PySide6':
        return True
    return not any(word in part for part in parts[1:] for word in UNUSED_QT)


a.binaries = [b for b in a.binaries if used(b)]
a.datas = [d for d in a.datas if used(d)]
pyz = PYZ(a.pure)

common = dict(
    name='DiscSplitter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICON],
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], upx=True, upx_exclude=[], runtime_tmpdir=None, **common)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, upx=False, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, upx_exclude=[], name='DiscSplitter')
