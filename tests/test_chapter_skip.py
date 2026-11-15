import core.models
from core import setlist

NL = "\n"


def chapters(lengths):
    out, t = [], 0.0
    for i, n in enumerate(lengths, 1):
        out.append(core.models.Chapter(i, t, t + n))
        t += n
    return out


def outline(parts):
    """parts: (seconds, level) -> 2 peaks per second; music varies around its level, talk stays low."""
    peaks = []
    for seconds, level in parts:
        peaks += [round(level * (0.85 + 0.3 * ((i * 7) % 10) / 10), 3) for i in range(int(seconds * 2))]
    return peaks


def test_loudness_separates_songs_from_talk():
    chs = chapters([20, 240, 300, 180, 600, 200, 90])
    wave = outline([(20, 0.002), (240, 0.15), (300, 0.13), (180, 0.14), (600, 0.012), (200, 0.15), (90, 0.01)])
    kinds = setlist.chapter_kinds(chs, wave, 2)
    assert [kinds[n] for n in range(1, 8)] == ['talk', 'music', 'music', 'music', 'talk', 'music', 'talk']


def test_without_an_outline_only_short_chapters_are_skipped():
    kinds = setlist.chapter_kinds(chapters([20, 240, 30, 300]), [], 2)
    assert kinds == {1: 'talk', 2: 'music', 3: 'talk', 4: 'music'}


def test_order_plan_passes_over_skipped_chapters():
    p = setlist.parse(NL.join(["1. A", "-MC-", "2. B", "3. C"]))
    plan = setlist.plan(p, chapters([20, 240, 600, 200, 300]), extras_take_chapter=False, skip_chapters=frozenset({1, 3}))
    assert [(e.index, e.name) for e in plan.entries] == [(2, 'A'), (4, 'B'), (5, 'C')]


def test_backend_skips_detected_talk_and_lets_chapters_be_switched(backend, qt_app):
    backend.disc.chapters = chapters([20, 240, 600, 200, 300])
    backend.disc.rebuild_chapters({})
    backend.preview._wave = outline([(20, 0.002), (240, 0.15), (600, 0.01), (200, 0.14), (300, 0.13)])
    backend.put(waveState='ready')
    text = NL.join(["1. A", "MC", "2. B", "3. C"])
    backend.names.previewPaste(text, {'skip': 'none'})   # "none" skips nothing
    assert backend.state['pastePreview']['skippedCount'] == 0
    backend.names.previewPaste(text, {})                 # by default detected non-songs are skipped
    assert backend.state['pastePreview']['skippedCount'] == 2
    backend.names.previewPaste(text, {'skip': 'auto'})
    pv = backend.state['pastePreview']
    assert pv['byWave'] and pv['skippedCount'] == 2
    assert [(c['number'], c['skipped'], c['title']) for c in pv['strip']] == [
        (1, True, ''), (2, False, 'A'), (3, True, ''), (4, False, 'B'), (5, False, 'C')]
    # Use chapter 3 after all: songs move along
    backend.names.previewPaste(text, {'skip': 'auto', 'chapters': {'3': 'use'}})
    strip = backend.state['pastePreview']['strip']
    assert [(c['number'], c['title'], c['manual']) for c in strip][2:4] == [(3, 'B', True), (4, 'C', False)]
    backend.names.applyPaste(text, {'skip': 'auto'})
    rows = {r['number']: r for r in backend.names.review_model.rows}
    assert [rows[n]['proposed'] for n in (2, 4, 5)] == ['A', 'B', 'C']
    assert rows[1]['confidence'] == 'extra' and not rows[1]['checked']
    assert rows[3]['confidence'] == 'extra' and not rows[3]['checked']
    assert backend.state['reviewChecked'] == 3


def test_chapter_kinds_tell_music_interlude_and_talk_apart():
    # 2 steps a second: a loud song, a quiet steady interlude, quiet choppy talk, a short middling sting
    spans = [(240, 0.5, 0.30), (120, 0.03, 0.30), (120, 0.04, 0.55), (60, 0.2, 0.30), (120, 0.03, 0.39)]
    peaks, ripple, chapters_, start = [], [], [], 0.0
    for n, (seconds, level, swing) in enumerate(spans, start=1):
        peaks += [level] * (seconds * 2)
        ripple += [swing] * (seconds * 2)
        chapters_.append(core.models.Chapter(n, start, start + seconds))
        start += seconds
    kinds = setlist.chapter_kinds(chapters_, peaks, 2, ripple)
    assert kinds == {1: 'music', 2: 'interlude', 3: 'talk', 4: 'interlude', 5: 'unsure'}
    # Without the ripple series quiet chapters fall back to talk
    assert setlist.chapter_kinds(chapters_, peaks, 2)[2] == 'talk'
