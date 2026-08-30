from src.models import PlayerState
from app.services.playback_controller import PlaybackController, PlaybackSource


def test_pause_resume_methods_exist_and_are_controller_owned():
    assert callable(getattr(PlaybackController, "pause"))
    assert callable(getattr(PlaybackController, "resume"))
    assert PlaybackSource.MANUAL.value == "MANUAL"


def test_transport_state_contract():
    assert PlayerState.PAUSED.value == "PAUSED"
    assert PlayerState.PLAYING.value == "PLAYING"
