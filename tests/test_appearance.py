import pytest

from gui import logic


@pytest.mark.parametrize('value, expected', [
    ('#f2a33a', '#F2A33A'),
    ('#FF0078D4', '#0078D4'),     # Qt colour strings may carry alpha
    (' #4fd1c5 ', '#4FD1C5'),
    ('system', 'system'),
    ('red', None),
    ('#12345', None),
    ('', None),
])
def test_normalize_accent(value, expected):
    assert logic.normalize_accent(value) == expected


@pytest.mark.parametrize('scale, expected', [
    ('system', None), ('1', '1'), ('1.5', '1.5'), ('1.75', '1.75'),
    ('3', None), (None, None),
])
def test_scale_factor(scale, expected):
    cfg = {} if scale is None else {'interface_scale': scale}
    assert logic.scale_factor(cfg) == expected


def test_old_relative_scale_key_is_ignored():
    # The earlier "ui_scale" key was relative to Windows scaling; it must not force a fixed scale.
    assert logic.scale_factor({'ui_scale': '1.25'}) is None


def test_appearance_preferences(backend):
    backend.setPreference('accent', '#0078d4')
    assert backend.config['accent'] == '#0078D4'
    backend.setPreference('accent', 'system')
    assert backend.config['accent'] == 'system'
    backend.setPreference('accent', 'not-a-colour')
    assert backend.config['accent'] == 'system'
    backend.setPreference('density', 'compact')
    backend.setPreference('interface_scale', '1.5')
    backend.setPreference('font_scale', '1.15')
    assert (backend.config['density'], backend.config['interface_scale'], backend.config['font_scale']) == ('compact', '1.5', '1.15')
    backend.setPreference('density', 'tiny')
    backend.setPreference('interface_scale', '4')
    backend.setPreference('font_scale', '2')
    assert (backend.config['density'], backend.config['interface_scale'], backend.config['font_scale']) == ('compact', '1.5', '1.15')
    backend.setPreference('interface_scale', 'system')
    assert backend.config['interface_scale'] == 'system'


def test_motion_preference(backend):
    for value in ('reduced', 'full'):
        backend.setPreference('motion', value)
        assert backend.config['motion'] == value
    backend.setPreference('motion', 'system')   # no longer an option
    assert backend.config['motion'] == 'full'


def test_new_defaults():
    from gui import settings
    assert settings.DEFAULTS['interface_scale'] == 'system'
    assert settings.DEFAULTS['font_scale'] == '1'
    assert settings.DEFAULTS['motion'] == 'full'


@pytest.mark.parametrize('ui_language, expected', [(0x0804, 'zh'), (0x0404, 'zh'), (0x0409, 'en'), (0x0411, 'en')])
def test_first_start_speaks_the_windows_language(tmp_path, monkeypatch, ui_language, expected):
    ctypes = pytest.importorskip('ctypes')
    if not hasattr(ctypes, 'windll'):
        pytest.skip('Windows only')
    from gui import settings
    monkeypatch.setattr(settings, 'SETTINGS_PATH', tmp_path / 'settings.json')
    monkeypatch.setattr(ctypes.windll.kernel32, 'GetUserDefaultUILanguage', lambda: ui_language)
    assert settings.load()['language'] == expected
    # Once settings are saved, the language in them is kept, whatever Windows shows.
    settings.save(dict(settings.load(), language='zh' if expected == 'en' else 'en'))
    assert settings.load()['language'] != expected
