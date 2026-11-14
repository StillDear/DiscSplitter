from gui.preview_session import PreviewSession, State


def start(session, target):
    return session.begin_render(target, lambda serial, cancel: (serial, cancel))


def test_render_then_arrive():
    s = PreviewSession()
    s.want('a.flac', ready=False)
    assert s.state is State.LOADING
    serial, _ = start(s, 'a.flac')
    assert s.end_render(serial) == 'a.flac' and s.arrived('a.flac')
    assert s.state is State.READY and not s.renders


def test_switching_clips_cancels_the_old_render_and_ignores_its_result():
    s = PreviewSession()
    s.want('a.flac', ready=False)
    old, cancel = start(s, 'a.flac')
    s.want('b.flac', ready=False)
    assert cancel.is_set()
    assert s.end_render(old) is None                  # already forgotten
    assert not s.arrived('a.flac') and s.state is State.LOADING


def test_prefetched_clip_survives_asking_for_it():
    s = PreviewSession()
    s.want('a.flac', ready=True)
    serial, cancel = start(s, 'b.flac')               # prefetch of the next chapter
    s.want('b.flac', ready=False)
    assert not cancel.is_set() and s.rendering('b.flac')
    assert s.end_render(serial) == 'b.flac' and s.arrived('b.flac')


def test_failure_and_stop():
    s = PreviewSession()
    s.listen = True
    s.want('a.flac', ready=False)
    serial, _ = start(s, 'a.flac')
    s.end_render(serial)
    assert s.failed('a.flac', 'ffmpeg: boom') and s.state is State.ERROR and s.error == 'ffmpeg: boom'
    s.stop()
    assert s.state is State.OFF and not s.listen and s.error == '' and not s.active
    assert not s.arrived('a.flac')                    # results after stop change nothing
