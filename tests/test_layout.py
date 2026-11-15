from gui import settings


def test_dragged_sizes_are_clamped_and_remembered(backend):
    backend.setLayoutSize('work_left', 330.4)
    backend.setLayoutSize('work_right', 9999)              # past the limit: clamped
    backend.setLayoutSize('preview_ratio', 0.05)
    backend.setLayoutSize('nonsense', 10)                  # unknown keys are ignored
    assert backend.config['layout'] == {'work_left': 330, 'work_right': 520, 'preview_ratio': 0.2}
    backend.setLayoutSize('work_left', -1)                 # double-click: back to the default
    assert 'work_left' not in backend.config['layout']


def test_layout_is_saved_once_dragging_settles(backend, qt_app, monkeypatch):
    saved = []
    monkeypatch.setattr(settings, 'save', lambda cfg: saved.append(dict(cfg['layout'])))
    backend.smoke = False
    for width in (250, 260, 270):
        backend.setLayoutSize('work_left', width)
    assert saved == []
    backend.layout_saver.timeout.emit()
    assert saved == [{'work_left': 270}]
