# -*- mode: python ; coding: utf-8 -*-
# Folder build for the Windows installer (packaging/build_installer.py runs this).
# The single-file portable exe is still built from DiscSplitter.spec in the project root.
import os

ROOT = os.path.dirname(SPECPATH)

a = Analysis(
    [os.path.join(ROOT, 'app.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(ROOT, 'qml'), 'qml'), (os.path.join(ROOT, 'disc_splitter.ico'), '.')],
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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DiscSplitter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(ROOT, 'disc_splitter.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DiscSplitter',
)
