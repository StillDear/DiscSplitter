import threading

import pytest

import core.jobs
import core.manifest
from gui.export_flow import ExportFlow, Phase
from test_backend import setup_disc, wait_idle
import core.sources


def test_happy_path_runs_once_and_finishes():
    flow = ExportFlow()
    assert flow.launch() is None                      # nothing prepared
    assert flow.prepare(dict(output='Album'))
    job = flow.launch()
    assert job == dict(output='Album') and flow.phase is Phase.RUNNING and flow.output == 'Album'
    assert isinstance(flow.cancel_event, threading.Event)
    assert not flow.prepare(dict(output='Other'))     # no new export while one runs
    assert flow.launch() is None
    assert flow.finish(failed=False, cancelled=False) == 'done'
    assert flow.phase is Phase.FINISHED and flow.cancel_event is None
    assert flow.finish(failed=False, cancelled=False) is None   # a stray second result is ignored


def test_cancel_only_while_running():
    flow = ExportFlow()
    assert not flow.cancel()
    flow.prepare(dict(output='Album'))
    flow.launch()
    event = flow.cancel_event
    assert flow.cancel() and event.is_set() and flow.result == 'cancelling'
    assert not flow.cancel()                          # already cancelling
    assert flow.finish(failed=True, cancelled=True) == 'cancelled'


@pytest.mark.parametrize('question', [Phase.CONFIRM_RESUME, Phase.CONFIRM_DUPLICATE, Phase.CONFIRM_COLLISION])
def test_dismissed_question_returns_to_idle(question):
    flow = ExportFlow()
    flow.prepare(dict(output='Album'))
    assert flow.ask(question)
    assert flow.abort()
    assert flow.phase is Phase.IDLE and flow.pending is None and flow.launch() is None


def test_questions_follow_the_documented_order():
    flow = ExportFlow()
    assert flow.ask(Phase.CONFIRM_COLLISION)
    assert not flow.ask(Phase.CONFIRM_DUPLICATE)      # never back to an earlier question
    assert not flow.go(Phase.FINISHED)


def test_backend_dismissing_resume_drops_the_question(backend, monkeypatch, tmp_path):
    from test_logic import manifest
    setup_disc(backend)
    backend.put(source='Album', output=str(tmp_path))
    output = tmp_path / 'Album'
    core.manifest.write_manifest(output / '_work', manifest(output, 'failed'))
    backend.exporter.startExport()
    assert backend.exporter.flow.phase is Phase.CONFIRM_RESUME
    backend.exporter.cancelExport()                            # Escape / Cancel on the resume dialog
    assert backend.exporter.flow.phase is Phase.IDLE


def test_failed_resume_does_not_leave_a_question_open(backend, qt_app, monkeypatch, tmp_path):
    from test_logic import manifest
    setup_disc(backend)
    m = manifest(tmp_path / 'Album', 'cancelled')
    core.manifest.write_manifest(tmp_path / 'Album' / '_work', m)
    backend.exporter.flow.manifest = m
    backend.exporter.flow.ask(Phase.CONFIRM_RESUME)
    monkeypatch.setattr(core.sources, 'inspect_playlist', lambda path, **_: (_ for _ in ()).throw(ValueError('gone')))
    errors = []
    backend.dialogRequested.connect(lambda kind, text: errors.append(text))
    backend.exporter.resume()
    wait_idle(backend, qt_app)
    assert errors == ['gone']
    assert backend.exporter.flow.phase is Phase.IDLE and backend.exporter.flow.pending is None


def test_rejected_job_leaves_no_running_badge(backend, qt_app):
    gate = threading.Event()
    backend.task(lambda p: gate.wait(5), lambda r: None)     # hold the worker
    before = dict(backend.state['pasteWeb'])
    backend.names.fetchSetlist('https://example.invalid/setlist')
    backend.metadata.metaSearch('musicbrainz', 'A', 'B', '')
    backend.testConnection()
    assert backend.state['pasteWeb'] == before
    assert backend.state['metaStatus'] == 'idle' and backend.state['netTest'] == []
    gate.set()
    wait_idle(backend, qt_app)
    assert backend.state['status'] == 'ready'


def test_progress_marks_the_interrupted_chapter(backend, tmp_path):
    setup_disc(backend)
    backend.exporter.progress(core.jobs.splitting(2, 'Two'))
    backend.exporter.progress(core.jobs.job_failed(RuntimeError('ffmpeg failed on chapter 2')))
    assert [r['status'] for r in backend.disc.chapter_model.rows] == ['pending', 'failed', 'pending']


def test_progress_events_survive_the_worker_signal(backend, qt_app):
    setup_disc(backend)
    backend.task(lambda progress: progress(core.jobs.splitting(3, 'Encore')), lambda r: None)
    wait_idle(backend, qt_app)
    assert backend.state['stage'] == 'splitting' and backend.state['current'] == 3
    assert backend.disc.chapter_model.rows[2]['status'] == 'running'
    assert backend.state['logs'].endswith('Splitting chapter 3: Encore')


def test_result_starts_idle(backend):
    assert backend.state['result'] == 'idle'
