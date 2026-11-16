"""Play styles of the heuristic bot.

A ``BotProfile`` holds every parameter of the ``BasicBot`` decisions. The
default values are exactly the original ``BasicBot`` behaviour; the presets
shift them to produce recognizable styles.
"""

from dataclasses import dataclass, fields

PROBABILITY_FIELDS = (
    "value_bet_probability",
    "medium_bet_probability",
    "bluff_probability",
    "raise_instead_of_call_probability",
    "bluff_raise_probability",
    "cbet_probability",
)


@dataclass(frozen=True)
class BotProfile:
    """Parameters of the heuristic decisions. Strengths range from 0 to 1."""

    # Facing a bet.
    raise_threshold: float = 0.9
    """Raise with at least this strength, whatever the price."""
    cheap_raise_threshold: float = 0.75
    """Raise with at least this strength when the call is cheap."""
    cheap_call_big_blinds: float = 3
    """A call of at most this many big blinds is cheap."""
    call_threshold: float = 0.75
    """Call any bet with at least this strength."""
    good_threshold: float = 0.5
    good_max_pot_odds: float = 0.4
    """A good hand calls when the pot odds do not exceed this share."""
    marginal_threshold: float = 0.3
    marginal_max_pot_odds: float = 0.25
    """A marginal hand calls when the pot odds do not exceed this share."""

    # Checked to.
    strong_bet_threshold: float = 0.75
    value_bet_probability: float = 0.85
    medium_bet_threshold: float = 0.5
    medium_bet_probability: float = 0.5
    bluff_probability: float = 0.08

    # Sizing and hand reading.
    raise_pot_fraction: float = 0.75
    bet_pot_fraction: float = 0.6
    multiway_penalty: float = 0.02
    """Strength lost per opponent beyond the first."""
    preflop_strength_bonus: float = 0.0
    """Added to the pre-flop strength: positive plays more hands."""

    # Extra aggression. At zero these draw no random number, which keeps
    # the original behaviour identical.
    raise_instead_of_call_probability: float = 0.0
    """Chance of raising a hand that would only call."""
    bluff_raise_probability: float = 0.0
    """Chance of raising a hand that would fold."""
    cbet_probability: float = 0.0
    """Chance of betting the flop as pre-flop aggressor when checked to."""

    def __post_init__(self) -> None:
        for name in PROBABILITY_FIELDS:
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1.")

        for name in ("raise_pot_fraction", "bet_pot_fraction", "cheap_call_big_blinds"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive.")

    @classmethod
    def parameter_names(cls) -> tuple[str, ...]:
        return tuple(field.name for field in fields(cls))


BASIC_PROFILE = BotProfile()

NIT_PROFILE = BotProfile(
    raise_threshold=0.93,
    cheap_raise_threshold=0.85,
    call_threshold=0.8,
    good_threshold=0.56,
    good_max_pot_odds=0.3,
    marginal_threshold=0.5,
    marginal_max_pot_odds=0.15,
    value_bet_probability=0.6,
    medium_bet_probability=0.2,
    bluff_probability=0.01,
)

TAG_PROFILE = BotProfile(
    raise_threshold=0.82,
    cheap_raise_threshold=0.68,
    call_threshold=0.7,
    good_threshold=0.55,
    marginal_threshold=0.42,
    marginal_max_pot_odds=0.2,
    value_bet_probability=0.9,
    medium_bet_probability=0.6,
    bluff_probability=0.1,
    raise_pot_fraction=0.8,
    preflop_strength_bonus=0.06,
    raise_instead_of_call_probability=0.2,
    cbet_probability=0.65,
)

LAG_PROFILE = BotProfile(
    raise_threshold=0.75,
    cheap_raise_threshold=0.6,
    call_threshold=0.65,
    good_threshold=0.45,
    good_max_pot_odds=0.45,
    marginal_threshold=0.3,
    value_bet_probability=0.9,
    medium_bet_probability=0.7,
    bluff_probability=0.25,
    raise_pot_fraction=0.85,
    preflop_strength_bonus=0.07,
    raise_instead_of_call_probability=0.35,
    bluff_raise_probability=0.06,
    cbet_probability=0.75,
)

CALLING_STATION_PROFILE = BotProfile(
    raise_threshold=0.97,
    cheap_raise_threshold=0.95,
    call_threshold=0.4,
    good_threshold=0.3,
    good_max_pot_odds=0.55,
    marginal_threshold=0.15,
    marginal_max_pot_odds=0.45,
    strong_bet_threshold=0.85,
    value_bet_probability=0.3,
    medium_bet_probability=0.05,
    bluff_probability=0.0,
    preflop_strength_bonus=0.02,
)

MANIAC_PROFILE = BotProfile(
    raise_threshold=0.6,
    cheap_raise_threshold=0.45,
    call_threshold=0.5,
    good_threshold=0.3,
    good_max_pot_odds=0.5,
    marginal_threshold=0.15,
    marginal_max_pot_odds=0.4,
    strong_bet_threshold=0.6,
    value_bet_probability=1.0,
    medium_bet_threshold=0.3,
    medium_bet_probability=0.9,
    bluff_probability=0.5,
    raise_pot_fraction=1.0,
    bet_pot_fraction=0.9,
    preflop_strength_bonus=0.1,
    raise_instead_of_call_probability=0.55,
    bluff_raise_probability=0.2,
    cbet_probability=0.9,
)
