from app.presentation import PresentationState


def test_guided_run_advances_and_finishes():
    state = PresentationState(slide_count=3)
    state.begin(0)
    assert state.complete(0) == 1
    state.begin(1)
    assert state.complete(1) == 2
    state.begin(2)
    assert state.complete(2) is None
    assert state.mode == "finished"


def test_resume_returns_to_bookmark_after_a_question_jumped_ahead():
    state = PresentationState(slide_count=6)
    state.begin(0)
    state.complete(0)
    state.begin(1)  # interrupted halfway through slide 2
    assert state.pause()
    state.current = 4  # the answer jumped to slide 5

    assert state.resume_index() == 1
    assert state.is_partial(1)


def test_resume_moves_past_a_finished_slide():
    state = PresentationState(slide_count=6)
    state.begin(2)
    state.complete(2)
    state.pause()
    assert state.resume_index() == 3


def test_resume_after_last_slide_has_nowhere_to_go():
    state = PresentationState(slide_count=2)
    state.begin(1)
    state.complete(1)
    assert state.resume_index() is None


def test_pause_only_applies_to_a_running_presentation():
    state = PresentationState(slide_count=2)
    assert not state.pause()
    state.begin(0)
    assert state.pause()
    assert not state.pause()
