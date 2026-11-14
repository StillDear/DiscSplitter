import os
import subprocess
import sys
from pathlib import Path

import pytest

from app import assert_qml_sources


def test_qml_icons_do_not_depend_on_font_glyphs():
    assert_qml_sources()


@pytest.mark.parametrize('code', [0x21BB, 0x25C9, 0x25CB, 0x25A1, 0x25CE, 0x2713])
def test_smoke_source_guard_rejects_each_font_icon(tmp_path, code):
    (tmp_path / 'Icon.qml').write_text(chr(code), encoding='utf-8')
    with pytest.raises(AssertionError, match='Font-dependent icon glyphs'):
        assert_qml_sources(tmp_path)


def test_main_and_qml_are_utf8_without_bom():
    for path in [Path('main.py'), *Path('qml').rglob('*.qml')]:
        source = path.read_bytes()
        assert not source.startswith(b'\xef\xbb\xbf'), path
        source.decode('utf-8')


def test_all_qml_screens_warning_strict_offscreen():
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    result = subprocess.run([sys.executable, 'app.py', '--smoke-test'], env=env,
                            capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'zero Qt/QML warnings' in result.stdout
