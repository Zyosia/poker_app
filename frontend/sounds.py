"""Sound effects of the tables: cards, chips, actions and the Spin & Go draw.

The sounds are short WAV files made by ``frontend.sound_synthesis`` (no
recorded asset). Qt's multimedia module is only loaded by a player created
with ``audio=True`` (the application), so the tests never open an audio
device: they read what a silent player was asked to play.
"""

from collections import deque
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QUrl

from backend.poker_engine.constants import ActionType
from backend.poker_engine.models import ActionEvent

if TYPE_CHECKING:
    from PySide6.QtMultimedia import QSoundEffect

SOUND_DIR = Path(__file__).resolve().parent / "assets" / "sounds"
RECENT_SOUNDS = 50
"""How many of the last sounds a player remembers (read by the tests)."""
JACKPOT_MULTIPLIER = 10
"""A Spin & Go prize from this multiplier on gets the big fanfare."""


class Sound(StrEnum):
    """Every sound effect; the value is the file name without ``.wav``."""

    DEAL = "deal"
    """The hole cards are dealt."""
    STREET = "street"
    """Flop, turn or river cards turned over."""
    CHECK = "check"
    FOLD = "fold"
    CALL = "call"
    BET = "bet"
    """A bet or a raise."""
    ALL_IN = "all_in"
    POT = "pot"
    """The pot is pushed to the winner."""
    TURN = "turn"
    """Your turn to act."""
    SPIN_TICK = "spin_tick"
    SPIN_PRIZE = "spin_prize"
    SPIN_JACKPOT = "spin_jackpot"

    @property
    def path(self) -> Path:
        return SOUND_DIR / f"{self.value}.wav"


ACTION_SOUNDS: dict[str, Sound] = {
    ActionType.FOLD: Sound.FOLD,
    ActionType.CHECK: Sound.CHECK,
    ActionType.CALL: Sound.CALL,
    ActionType.RAISE: Sound.BET,
    ActionType.ALL_IN: Sound.ALL_IN,
}


def action_sound(event: ActionEvent) -> Sound | None:
    """The sound of a player's action; None for the forced bets."""
    return ACTION_SOUNDS.get(event.action)


def spin_prize_sound(multiplier: int) -> Sound:
    return Sound.SPIN_JACKPOT if multiplier >= JACKPOT_MULTIPLIER else Sound.SPIN_PRIZE


def missing_sounds() -> list[Sound]:
    """The sounds whose file is absent, e.g. a build made without the folder."""
    return [sound for sound in Sound if not sound.path.is_file()]


class SoundPlayer(QObject):
    """Plays the sound effects at the user's volume.

    Without ``audio`` nothing is heard and Qt's multimedia module is never
    loaded; the sounds asked for are still remembered in ``recent``. With
    ``audio``, the sounds whose file is absent are listed in ``missing``.
    """

    def __init__(self, audio: bool = False, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.enabled = True
        self.volume = 0.7
        """0.0 to 1.0, as the user sees it (the loudness is not linear)."""
        self.recent: deque[Sound] = deque(maxlen=RECENT_SOUNDS)
        self._effects: dict[Sound, QSoundEffect] = {}
        self.missing: list[Sound] = []

        if audio:
            self.missing = missing_sounds()
            self._load_effects()

    @property
    def has_audio(self) -> bool:
        return bool(self._effects)

    def set_volume(self, volume: float) -> None:
        self.volume = min(1.0, max(0.0, volume))

    def play(self, sound: Sound) -> None:
        if not self.enabled or self.volume <= 0:
            return

        self.recent.append(sound)
        effect = self._effects.get(sound)

        if effect is not None:
            # A square curve: half way on the slider sounds about half as loud.
            effect.setVolume(self.volume**2)
            effect.play()

    def _load_effects(self) -> None:
        from PySide6.QtMultimedia import QSoundEffect

        for sound in Sound:
            if sound in self.missing:
                continue

            effect = QSoundEffect(self)
            effect.setSource(QUrl.fromLocalFile(str(sound.path)))
            self._effects[sound] = effect
