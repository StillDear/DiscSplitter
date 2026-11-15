from contextlib import contextmanager
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl

from core import bluray_iso
import core.models
from test_backend import wait_idle
import core.chapter_marks
import core.sources
import core.split
import core.tools


@pytest.mark.skipif(os.name != 'nt', reason='Windows ISO drive paths')
@pytest.mark.parametrize('owned', [False, True])
def test_mount_cleanup_preserves_existing_mounts(tmp_path, monkeypatch, owned):
    image = tmp_path / 'concert.iso'
    image.touch()
    commands = []

    def powershell(script, path):
        assert path == image.resolve()
        commands.append(script)
        return f'DTS_ISO:R:{int(owned)}\n'

    monkeypatch.setattr(bluray_iso, '_powershell', powershell)
    with pytest.raises(ValueError, match='scan failed'):
        with bluray_iso.mounted(image) as root:
            assert root == Path('R:/')
            raise ValueError('scan failed')
    assert len(commands) == (2 if owned else 1)
    if owned:
        assert commands[-1].startswith('Dismount-DiskImage ')


def test_iso_import_and_resume_survive_drive_changes(backend, qt_app, tmp_path, monkeypatch):
    image = tmp_path / 'Artist - Concert.ISO'
    image.touch()
    sidecar = tmp_path / 'tracks.txt'
    sidecar.write_text('One', encoding='utf-8')
    relative = Path('BDMV/PLAYLIST/00001.mpls')
    mounts = []

    @contextmanager
    def mounted(path):
        assert path == image.resolve()
        root = tmp_path / f'mount{len(mounts)}'
        playlist = root / relative
        playlist.parent.mkdir(parents=True)
        playlist.touch()
        mounts.append(playlist)
        yield root

    audio = core.models.Track(1, 'audio', 'LPCM')
    chapters = [core.models.Chapter(1, 0, 30)]
    monkeypatch.setattr(bluray_iso, 'mounted', mounted)
    monkeypatch.setattr(core.sources, 'inspect_playlist', lambda path, **_: core.models.Playlist(path, [audio], 1, 30))
    read_paths = []
    monkeypatch.setattr(core.chapter_marks, 'read_chapters_from_source', lambda path, **kw: read_paths.append(path) or chapters)
    monkeypatch.setattr(core.tools, 'tool_versions', lambda: {})
    extracted = []

    def split(source, *_args, **kwargs):
        # MKV exports cut straight from the mounted playlist (no intermediate file).
        extracted.append(source)
        if len(extracted) == 1:
            raise RuntimeError('Simulated interruption')
        return []

    monkeypatch.setattr(core.split, 'split_mkv_direct', split)

    backend.disc.setSource(QUrl.fromLocalFile(str(image)).toString())
    wait_idle(backend, qt_app)
    assert backend.disc.playlist.path == relative
    assert read_paths == [mounts[1]]
    assert backend.state['album'] == 'Concert'
    assert backend.state['sidecars'] == [str(sidecar)]

    backend.disc.setOutput(str(tmp_path / 'library'))
    backend.disc.setAllChapters(True)
    backend.exporter.startExport()
    wait_idle(backend, qt_app)
    assert backend.exporter.flow.manifest.source_iso == str(image.resolve())
    assert Path(backend.exporter.flow.manifest.source_playlist) == relative
    assert extracted == [mounts[2]]

    backend.exporter.resume()
    wait_idle(backend, qt_app)
    assert backend.state['result'] == 'done'
    assert extracted == [mounts[2], mounts[4]]
