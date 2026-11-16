"""The built-in help: both languages say the same things, the menu reaches every section, and a bug report
carries what is needed without anything personal."""
import getpass
import os
import urllib.parse
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from gui import help_content
from gui.i18n import EN, ZH


def test_languages_have_the_same_sections_and_entries():
    assert set(help_content.ZH) == set(help_content.EN) == set(help_content.SECTIONS)
    for section in help_content.SECTIONS:
        zh, en = help_content.ZH[section], help_content.EN[section]
        assert len(zh) == len(en) > 0, section
        for zh_entry, en_entry in zip(zh, en):
            assert set(zh_entry) == set(en_entry) == {'title', 'body'}
            assert all(value.strip() for value in (*zh_entry.values(), *en_entry.values()))


def test_help_texts_and_interface_texts_are_paired():
    assert set(ZH) == set(EN)
    for key in ('helpGuide', 'helpFaq', 'helpTroubleshoot', 'projectHome', 'aboutApp', 'diagSummary', 'issueTemplate'):
        assert ZH[key] and EN[key]


def test_buttons_named_in_the_help_exist_in_the_interface():
    """A tip that says "click X" must name a button the reader can find, in the same language."""
    named = {'zh': ['获取曲名', '只选已改名', '不选未命名', '恢复原始章节', '按条码搜索', '粘贴曲目', '识别截图…',
                    '去掉括号', '检查连接', '重新检测', '浏览', '选择文件夹', '选择 ISO / MKV'],
             'en': ['Get titles', 'Only renamed', 'Skip unnamed', 'Restore original chapters', 'Search by barcode',
                    'Paste list', 'Read a screenshot…', 'Remove brackets', 'Check connection', 'Check again', 'Browse',
                    'Choose folder', 'Choose ISO / MKV']}
    for language, labels in named.items():
        interface = set((ZH if language == 'zh' else EN).values())
        text = ' '.join(e['body'] for entries in help_content.CONTENT[language].values() for e in entries)
        for label in labels:
            assert label in interface, label
            assert label in text, label


@pytest.mark.parametrize('topic', ['guide', 'tips', 'faq', 'troubleshoot', 'about'])
def test_menu_topics_open_the_help_page_on_their_section(backend, topic):
    backend.help(topic)
    assert backend.state['page'] == 'help'
    assert backend.state['helpSection'] == topic


def test_help_over_settings_keeps_both_ways_back(backend):
    backend.navigate('settings')
    assert backend.state['returnPage'] == 'start'
    backend.help('guide')
    backend.back()
    assert backend.state['page'] == 'settings'
    backend.back()
    assert backend.state['page'] == 'start'


def test_help_from_start_goes_back_to_start(backend):
    backend.help('faq')
    backend.back()
    assert backend.state['page'] == 'start'


def test_browser_links(backend, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url.toString()))
    backend.setPreference('language', 'zh')
    backend.help('readme')
    backend.setPreference('language', 'en')
    backend.help('readme')
    backend.help('report')
    assert opened[0].endswith('/blob/main/README.zh-CN.md')
    assert opened[1].endswith('#readme')
    assert '/issues/new?body=' in opened[2]
    assert backend.state['page'] == 'start'      # links leave the app; the page stays


def test_diagnostics_hold_nothing_personal(backend):
    text = backend.diagnostics()
    assert text.startswith('DiscSplitter ')
    assert 'Windows' in text and 'Tools:' in text
    for private in (str(Path.home()), getpass.getuser(), os.environ.get('USERPROFILE', '\0')):
        assert private.lower() not in text.lower()


def test_issue_body_carries_the_template_and_diagnostics(backend):
    backend.setPreference('language', 'en')
    query = urllib.parse.urlparse(backend.issue_url()).query
    body = urllib.parse.parse_qs(query)['body'][0]
    assert body.startswith('## What happened')
    assert backend.diagnostics() in body


def test_log_folder_is_made_and_opened(backend, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url))
    backend.openLogFolder()
    folder = backend.exporter.LOG_DIR
    assert folder.is_dir()
    assert opened == [QUrl.fromLocalFile(str(folder))]


def test_copy_puts_diagnostics_on_the_clipboard(backend, qt_app):
    backend.copyDiagnostics()
    assert qt_app.clipboard().text() == backend.diagnostics()
