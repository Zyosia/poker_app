"""Makes the sound effects' WAV files, with the standard library only.

Run ``python -m frontend.sound_synthesis`` to write them again in
``frontend/assets/sounds``. The sounds are built from a few simple pieces:
filtered noise for the cards, short ringing tones for the chips, a damped low
tone for a knock on the table and bell tones for the alerts. A fixed seed
makes every run write the same sounds.
"""

import math
import random
import struct
import wave
from collections.abc import Callable
from pathlib import Path

from frontend.sounds import SOUND_DIR, Sound

SAMPLE_RATE = 44_100
Samples = list[float]


def silence(seconds: float) -> Samples:
    return [0.0] * int(seconds * SAMPLE_RATE)


def mix(target: Samples, source: Samples, start: float, gain: float = 1.0) -> None:
    """Add ``source`` into ``target`` from ``start`` seconds on."""
    offset = int(start * SAMPLE_RATE)

    for index, value in enumerate(source[: max(0, len(target) - offset)]):
        target[offset + index] += value * gain


def band_pass(samples: Samples, center: float, q: float) -> Samples:
    """A resonant band-pass filter (the classic biquad)."""
    omega = 2 * math.pi * center / SAMPLE_RATE
    alpha = math.sin(omega) / (2 * q)
    a0 = 1 + alpha
    b0, b2 = alpha / a0, -alpha / a0
    a1, a2 = -2 * math.cos(omega) / a0, (1 - alpha) / a0
    x1 = x2 = y1 = y2 = 0.0
    filtered = []

    for x in samples:
        y = b0 * x + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, x
        y2, y1 = y1, y
        filtered.append(y)

    return filtered


def envelope(attack: float, decay: float) -> Callable[[int], float]:
    """A linear rise over ``attack`` seconds, then an exponential decay."""
    attack_samples = max(1, int(attack * SAMPLE_RATE))

    def level(index: int) -> float:
        if index < attack_samples:
            return index / attack_samples

        return math.exp(-(index - attack_samples) / (decay * SAMPLE_RATE))

    return level


def noise_burst(
    rng: random.Random,
    seconds: float,
    center: float,
    q: float,
    attack: float,
    decay: float,
) -> Samples:
    count = int(seconds * SAMPLE_RATE)
    level = envelope(attack, decay)
    noise = [rng.uniform(-1, 1) * level(index) for index in range(count)]

    return band_pass(noise, center, q)


def tone(
    frequencies: tuple[float, ...],
    seconds: float,
    attack: float,
    decay: float,
    gains: tuple[float, ...] | None = None,
) -> Samples:
    """Damped sine partials: a chip, a knock or a bell, by their frequencies."""
    count = int(seconds * SAMPLE_RATE)
    level = envelope(attack, decay)
    gains = gains or (1.0,) * len(frequencies)
    partials = list(
        zip(
            (2 * math.pi * frequency / SAMPLE_RATE for frequency in frequencies),
            gains,
            strict=True,
        )
    )

    return [
        level(index) * sum(gain * math.sin(step * index) for step, gain in partials)
        for index in range(count)
    ]


def normalized(samples: Samples, peak: float) -> Samples:
    highest = max(abs(value) for value in samples) or 1.0
    fade = int(0.004 * SAMPLE_RATE)  # No click when the sound stops.

    for index in range(1, fade + 1):
        samples[-index] *= (index - 1) / fade

    return [value * peak / highest for value in samples]


# --- The pieces -------------------------------------------------------------


def card_flick(rng: random.Random, length: float = 0.07) -> Samples:
    """A card sliding off the deck: bright noise, a quick attack."""
    flick = noise_burst(rng, length, 3_200, 0.9, 0.003, length / 4)
    slap = noise_burst(rng, length, 900, 1.4, 0.001, 0.012)
    mix(flick, slap, 0.0, 0.6)

    return flick


def chip_click(rng: random.Random) -> Samples:
    """Two clay chips touching: a few high partials ringing very briefly."""
    base = rng.uniform(2_600, 3_400)
    partials = (base, base * 1.47, base * 2.09, base * 2.83)
    click = tone(partials, 0.05, 0.0005, rng.uniform(0.010, 0.016), (1, 0.7, 0.45, 0.3))
    mix(click, noise_burst(rng, 0.01, 6_000, 0.8, 0.0003, 0.002), 0.0, 0.5)

    return click


def chips(rng: random.Random, count: int, spread: float, seconds: float) -> Samples:
    samples = silence(seconds)
    start = 0.0

    for _ in range(count):
        mix(samples, chip_click(rng), start, rng.uniform(0.6, 1.0))
        start += rng.uniform(spread * 0.5, spread * 1.5)

    return samples


def knock(rng: random.Random) -> Samples:
    """A knuckle on the felt: a damped low tone and a soft thud."""
    low = tone((170, 310, 520), 0.12, 0.001, 0.025, (1, 0.5, 0.2))
    mix(low, noise_burst(rng, 0.03, 700, 1.0, 0.0005, 0.006), 0.0, 0.8)

    return low


def bell(frequency: float, seconds: float, decay: float) -> Samples:
    return tone(
        (frequency, frequency * 2, frequency * 3.01),
        seconds,
        0.004,
        decay,
        (1, 0.35, 0.12),
    )


# --- The sounds -------------------------------------------------------------


def make_deal(rng: random.Random) -> Samples:
    samples = silence(0.32)
    mix(samples, card_flick(rng), 0.0)
    mix(samples, card_flick(rng), 0.14, 0.9)

    return samples


def make_street(rng: random.Random) -> Samples:
    samples = silence(0.22)
    mix(samples, card_flick(rng, 0.09), 0.0)
    mix(samples, noise_burst(rng, 0.05, 1_200, 1.2, 0.001, 0.01), 0.07, 0.7)

    return samples


def make_check(rng: random.Random) -> Samples:
    samples = silence(0.3)
    mix(samples, knock(rng), 0.0)
    mix(samples, knock(rng), 0.13, 0.85)

    return samples


def make_fold(rng: random.Random) -> Samples:
    """Cards pushed away: a soft swish going down."""
    count = int(0.24 * SAMPLE_RATE)
    level = envelope(0.05, 0.05)
    noise = [rng.uniform(-1, 1) * level(index) for index in range(count)]

    return band_pass(noise, 1_800, 0.7)


def make_pot(rng: random.Random) -> Samples:
    """The pot slid to the winner: a long swish and chips settling."""
    samples = silence(0.75)
    swish = make_fold(rng)
    mix(samples, swish, 0.0, 0.6)
    mix(samples, chips(rng, 9, 0.05, 0.75), 0.12)

    return samples


def make_turn(rng: random.Random) -> Samples:
    samples = silence(0.6)
    mix(samples, bell(880, 0.6, 0.12), 0.0)
    mix(samples, bell(1_318.5, 0.5, 0.14), 0.11)

    return samples


def make_spin_tick(rng: random.Random) -> Samples:
    return tone((1_900, 3_100), 0.04, 0.0005, 0.006, (1, 0.4))


def arpeggio(notes: tuple[float, ...], step: float, seconds: float) -> Samples:
    samples = silence(seconds)

    for index, frequency in enumerate(notes):
        mix(samples, bell(frequency, seconds - index * step, 0.35), index * step)

    return samples


C_MAJOR = (523.25, 659.25, 783.99, 1_046.5)


def make_spin_prize(rng: random.Random) -> Samples:
    return arpeggio(C_MAJOR, 0.09, 1.1)


def make_spin_jackpot(rng: random.Random) -> Samples:
    """Two rising runs, then the chord rings with chips falling."""
    samples = silence(2.2)
    mix(samples, arpeggio(C_MAJOR, 0.07, 0.6), 0.0, 0.8)
    mix(samples, arpeggio((*C_MAJOR[1:], 1_318.5), 0.07, 0.6), 0.3, 0.8)

    for frequency in (*C_MAJOR, 1_318.5):
        mix(samples, bell(frequency, 1.6, 0.5), 0.62, 0.5)

    mix(samples, chips(rng, 14, 0.06, 1.2), 0.7, 0.5)

    return samples


SOUNDS: dict[Sound, tuple[Callable[[random.Random], Samples], float]] = {
    Sound.DEAL: (make_deal, 0.55),
    Sound.STREET: (make_street, 0.55),
    Sound.CHECK: (make_check, 0.6),
    Sound.FOLD: (make_fold, 0.35),
    Sound.CALL: (lambda rng: chips(rng, 3, 0.05, 0.3), 0.6),
    Sound.BET: (lambda rng: chips(rng, 5, 0.045, 0.4), 0.65),
    Sound.ALL_IN: (lambda rng: chips(rng, 16, 0.035, 0.8), 0.7),
    Sound.POT: (make_pot, 0.6),
    Sound.TURN: (make_turn, 0.45),
    Sound.SPIN_TICK: (make_spin_tick, 0.35),
    Sound.SPIN_PRIZE: (make_spin_prize, 0.55),
    Sound.SPIN_JACKPOT: (make_spin_jackpot, 0.65),
}
"""How each sound is made, and its peak level (0 to 1)."""


def write_wav(path: Path, samples: Samples) -> None:
    frames = b"".join(
        struct.pack("<h", round(max(-1.0, min(1.0, value)) * 32_767))
        for value in samples
    )

    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(SAMPLE_RATE)
        file.writeframes(frames)


def write_sounds(folder: Path = SOUND_DIR, seed: int = 2026) -> None:
    folder.mkdir(parents=True, exist_ok=True)

    for sound, (make, peak) in SOUNDS.items():
        rng = random.Random(f"{seed}-{sound.value}")
        write_wav(folder / f"{sound.value}.wav", normalized(make(rng), peak))


if __name__ == "__main__":
    write_sounds()
    print(f"{len(SOUNDS)} sounds written in {SOUND_DIR}")
