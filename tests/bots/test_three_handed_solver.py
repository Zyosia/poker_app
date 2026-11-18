"""Three-handed push/fold (Monte Carlo CFR) and push/fold with antes (V2.x)."""

import pytest

from backend.application.ranges import HandRange
from backend.bots.push_fold_solutions import HEADS_UP_RANGES, THREE_HANDED_RANGES
from backend.bots.push_fold_solver import (
    HEADS_UP_ANTES,
    THREE_HANDED_ANTES,
    combo_pair_counts,
    equity_matrix,
    exploitability,
    solve,
)
from backend.bots.three_handed_solver import (
    BIG,
    BUTTON,
    SMALL,
    Spot,
    ThreeHandedStrategy,
    _result,
    solve_three_handed,
)


def share(notation: str) -> float:
    return HandRange.parse(notation).share if notation else 0.0


# --- The results of a deal --------------------------------------------------------------


def test_a_lone_shove_takes_the_blinds_and_antes() -> None:
    posted = (0.1, 0.6, 1.1)  # Classic antes of 0.1.
    ranks = ((1,), (0,), (0,))

    assert _result((BUTTON,), ranks, posted, 10) == pytest.approx((1.7, -0.6, -1.1))


def test_showdowns_share_the_pot_and_the_dead_money() -> None:
    posted = (0.0, 0.5, 1.0)
    ranks = ((2,), (1,), (2,))

    # The button and the big blind tie; the small blind's half blind is dead.
    assert _result((BUTTON, SMALL, BIG), ranks, posted, 10) == pytest.approx(
        (5.0, -10.0, 5.0)
    )
    assert _result((BUTTON, BIG), ranks, posted, 10) == pytest.approx(
        (0.25, -0.5, 0.25)
    )


def test_chips_are_never_created() -> None:
    posted = (0.0, 0.5, 2.0)

    for players in ((BUTTON,), (SMALL, BIG), (BUTTON, SMALL, BIG), (BUTTON, BIG)):
        for ranks in (((3,), (2,), (1,)), ((1,), (3,), (3,))):
            assert sum(_result(players, ranks, posted, 8)) == pytest.approx(0.0)


# --- Solving -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def solved() -> ThreeHandedStrategy:
    return solve_three_handed(stack=10, iterations=60_000, seed=1)


def test_strong_hands_shove_and_weak_hands_fold(solved: ThreeHandedStrategy) -> None:
    aces, trash = HandRange.parse("AA"), "72o"
    hands = list(solved.range_at(Spot.SMALL_BLIND_SHOVES))

    assert aces.labels <= solved.range_at(Spot.BUTTON_SHOVES)
    assert aces.labels <= solved.range_at(Spot.BIG_BLIND_CALLS_BOTH)
    assert trash not in solved.range_at(Spot.BUTTON_SHOVES)
    assert trash not in solved.range_at(Spot.BIG_BLIND_CALLS_BOTH)
    assert hands  # Folded to, the small blind shoves something.


def test_the_solution_is_reproducible() -> None:
    first = solve_three_handed(stack=6, iterations=3_000, seed=4)
    second = solve_three_handed(stack=6, iterations=3_000, seed=4)

    assert first == second


def test_antes_widen_the_heads_up_ranges() -> None:
    weights = combo_pair_counts()
    equity = equity_matrix(samples=2, seed=1)
    plain = solve(equity, weights, 12, 120)
    classic = solve(equity, weights, 12, 120, antes=HEADS_UP_ANTES["classic"])

    assert len(classic.push_range()) > len(plain.push_range())
    assert exploitability(classic, equity, weights) < 0.01


# --- The precomputed solutions ------------------------------------------------------------


def test_every_ante_has_its_solutions() -> None:
    assert set(HEADS_UP_RANGES) == set(HEADS_UP_ANTES)
    assert set(THREE_HANDED_RANGES) == set(THREE_HANDED_ANTES)

    for depths in THREE_HANDED_RANGES.values():
        assert all(len(ranges) == len(Spot) for ranges in depths.values())


def test_antes_make_everyone_shove_and_call_wider() -> None:
    for depth in (8, 15):
        plain = HEADS_UP_RANGES["none"][depth]
        classic = HEADS_UP_RANGES["classic"][depth]
        big_blind_ante = HEADS_UP_RANGES["big_blind"][depth]

        assert share(classic[0]) > share(plain[0])
        assert share(classic[1]) > share(plain[1])
        # The big blind has two big blinds in: it calls far wider (so the
        # small blind cannot always shove wider).
        assert share(big_blind_ante[1]) > share(plain[1]) + 0.05

    plain = THREE_HANDED_RANGES["none"][10]
    antes = THREE_HANDED_RANGES["big_blind"][10]
    assert share(antes[Spot.BUTTON_SHOVES]) > share(plain[Spot.BUTTON_SHOVES])


def test_three_handed_ranges_are_tighter_than_heads_up() -> None:
    """With a player more behind, the button shoves less than heads-up."""
    for depth in (5, 10, 15):
        heads_up_push = share(HEADS_UP_RANGES["none"][depth][0])
        button_push = share(THREE_HANDED_RANGES["none"][depth][Spot.BUTTON_SHOVES])
        small_push = share(THREE_HANDED_RANGES["none"][depth][Spot.SMALL_BLIND_SHOVES])

        assert button_push < small_push <= heads_up_push + 0.05
        both = share(THREE_HANDED_RANGES["none"][depth][Spot.BIG_BLIND_CALLS_BOTH])
        one = share(THREE_HANDED_RANGES["none"][depth][Spot.BIG_BLIND_CALLS_BUTTON])
        assert both < one  # Against two all-ins, the big blind calls tighter.
