"""Sound effects: the files, what each event plays, and the volume.

The tests never open an audio device: the screens get a silent
``SoundPlayer``, which still remembers the sounds it was asked to play.
"""

import random
import wave
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from backend.poker_engine.constants import ActionType, Street
from backend.poker_engine.models import ActionEvent
from frontend.sound_synthesis import SAMPLE_RATE, write_sounds
from frontend.sounds import Sound, SoundPlayer, action_sound, spin_prize_sound
from frontend.ui.game_screen import GameScreen
from frontend.ui.main_window import MainWindow
from tests.frontend.test_game_screen import HUMAN, make_game

ProcessUntil = Callable[[Callable[[], bool]], None]


def event(action: str) -> ActionEvent:
    return ActionEvent(
        sequence=1,
        street=Street.PREFLOP,
        player="Bot1",
        position=None,
        action=action,
        amount=10,
        bet_before=0,
        bet_after=10,
        pot_after=25,
        current_bet_after=10,
    )


def read_wav(path: Path) -> tuple[wave._wave_params, list[int]]:
    with wave.open(str(path)) as file:
        params = file.getparams()
        frames = file.readframes(params.nframes)

    samples = [
        int.from_bytes(frames[index : index + 2], "little", signed=True)
        for index in range(0, len(frames), 2)
    ]

    return params, samples


# --- The files ---------------------------------------------------------------


@pytest.mark.parametrize("sound", list(Sound))
def test_every_sound_is_a_short_mono_wav_file(sound: Sound) -> None:
    params, samples = read_wav(sound.path)
    peak = max(abs(sample) for sample in samples) / 32_767

    assert (params.nchannels, params.sampwidth) == (1, 2)
    assert params.framerate == SAMPLE_RATE
    assert 0.03 <= params.nframes / SAMPLE_RATE <= 2.5
    assert 0.2 <= peak <= 0.8  # Audible, never clipped.
    assert samples[-1] == 0  # Faded out: no click at the end.


def test_the_synthesis_writes_every_sound(tmp_path: Path) -> None:
    write_sounds(tmp_path)

    for sound in Sound:
        written, _ = read_wav(tmp_path / f"{sound.value}.wav")
        shipped, _ = read_wav(sound.path)
        assert written.nframes == shipped.nframes


# --- What plays --------------------------------------------------------------


def test_each_decision_has_its_sound_and_forced_bets_have_none() -> None:
    assert action_sound(event(ActionType.FOLD)) == Sound.FOLD
    assert action_sound(event(ActionType.CHECK)) == Sound.CHECK
    assert action_sound(event(ActionType.CALL)) == Sound.CALL
    assert action_sound(event(ActionType.RAISE)) == Sound.BET
    assert action_sound(event(ActionType.ALL_IN)) == Sound.ALL_IN
    assert action_sound(event("post_sb")) is None
    assert action_sound(event("post_ante")) is None


def test_a_big_spin_multiplier_gets_the_fanfare() -> None:
    assert spin_prize_sound(2) == Sound.SPIN_PRIZE
    assert spin_prize_sound(5) == Sound.SPIN_PRIZE
    assert spin_prize_sound(10) == Sound.SPIN_JACKPOT
    assert spin_prize_sound(1000) == Sound.SPIN_JACKPOT


def test_a_disabled_or_muted_player_plays_nothing(qapp: QApplication) -> None:
    player = SoundPlayer()
    player.play(Sound.DEAL)
    player.enabled = False
    player.play(Sound.FOLD)
    player.enabled = True
    player.set_volume(0)
    player.play(Sound.CHECK)

    assert list(player.recent) == [Sound.DEAL]


def test_the_volume_stays_between_zero_and_one(qapp: QApplication) -> None:
    player = SoundPlayer()
    player.set_volume(1.7)
    assert player.volume == 1.0
    player.set_volume(-0.2)
    assert player.volume == 0.0


# --- At the table ------------------------------------------------------------


@pytest.fixture
def screen(qapp: QApplication) -> GameScreen:
    game_screen = GameScreen()
    game_screen.step_delay_ms = 0

    return game_screen


def test_a_hand_plays_the_deal_your_turn_actions_streets_and_pot(
    screen: GameScreen, process_until: ProcessUntil
) -> None:
    game = make_game(dealer_index=1)  # Hero is the Big Blind.
    screen.start_game(game, human_name=HUMAN)
    process_until(lambda: game.is_waiting_for_human)

    # The Button and the Small Blind (passive bots) call: the Big Blind acts.
    assert list(screen.sounds.recent) == [
        Sound.DEAL,
        Sound.CALL,
        Sound.CALL,
        Sound.TURN,
    ]

    hand = game.hand
    assert hand is not None

    while not hand.finished:  # Hero checks every street down.
        if game.is_waiting_for_human:
            screen.action_panel.call_button.click()

        process_until(lambda: game.is_waiting_for_human or hand.finished)

    assert Sound.CHECK in screen.sounds.recent
    assert screen.sounds.recent.count(Sound.STREET) == 3  # Flop, turn, river.
    assert screen.sounds.recent[-1] == Sound.POT


def test_your_turn_sounds_once_even_after_a_pause(
    screen: GameScreen, process_until: ProcessUntil
) -> None:
    game = make_game(dealer_index=0)  # Hero, the Button, acts first.
    screen.start_game(game, human_name=HUMAN)
    process_until(lambda: game.is_waiting_for_human)

    screen.toggle_pause()
    screen.toggle_pause()

    assert screen.sounds.recent.count(Sound.TURN) == 1


def test_no_turn_sound_when_the_alert_is_off(
    screen: GameScreen, process_until: ProcessUntil
) -> None:
    screen.turn_alert = False
    game = make_game(dealer_index=0)
    screen.start_game(game, human_name=HUMAN)
    process_until(lambda: game.is_waiting_for_human)

    assert Sound.TURN not in screen.sounds.recent


def test_the_spin_draw_ticks_then_plays_the_prize(qapp: QApplication) -> None:
    window = MainWindow(save_sessions=False, rng=random.Random(12))
    window.main_menu.card("spin").click()
    window.spin_setup_screen.start_button.click()
    screen = window.tournament_screen

    while screen._reveal_values:  # noqa: SLF001 - run the animation instantly
        screen._reveal_tick()  # noqa: SLF001

    multiplier = screen.tournament.multiplier
    assert multiplier is not None
    sounds = list(window.sounds.recent)
    assert sounds[0] == Sound.SPIN_TICK
    assert sounds[-1] == spin_prize_sound(multiplier.value)
    assert set(sounds[:-1]) == {Sound.SPIN_TICK}


def test_the_window_shares_its_player_with_the_tables(qapp: QApplication) -> None:
    window = MainWindow(save_sessions=False)

    assert window.game_screen.sounds is window.sounds
    assert window.tournament_screen.sounds is window.sounds
    assert window.sounds.has_audio is False  # Tests never open an audio device.
