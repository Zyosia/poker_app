"""Equity of hands face up: exact counts, and the pre-flop estimate."""

import random

import pytest

from backend.application import equity
from backend.application.equity import ESTIMATE_EVALUATIONS, calculate_equity
from backend.poker_engine.hand_evaluator import HandCategory, evaluate_rank

ACES = ("AH", "AD")
KINGS = ("KC", "KS")


def test_one_card_to_come_is_counted_exactly() -> None:
    # Only the two kings left among 44 cards win for KK.
    equity = calculate_equity([ACES, KINGS], ["2C", "7D", "9H", "QS"])

    assert equity.exact
    assert equity.shares == pytest.approx((42 / 44, 2 / 44))


def test_two_cards_to_come_are_counted_exactly() -> None:
    equity = calculate_equity([ACES, KINGS], ["2C", "7D", "9H"])

    assert equity.exact
    assert sum(equity.shares) == pytest.approx(1)
    assert 0.9 < equity.shares[0] < 0.93


def test_a_complete_board_has_a_winner_or_a_split() -> None:
    assert calculate_equity([ACES, KINGS], ["2C", "7D", "9H", "QS", "3D"]).shares == (
        1.0,
        0.0,
    )

    board = ["TC", "JD", "QH", "KD", "AS"]  # Broadway on the board: a split.
    assert calculate_equity([("2C", "3C"), ("4D", "5D")], board).shares == (
        0.5,
        0.5,
    )


def test_the_preflop_estimate_uses_its_own_rng() -> None:
    random.seed(7)
    expected_next = random.random()
    random.seed(7)

    first = calculate_equity([ACES, KINGS], [], seed=11)
    second = calculate_equity([ACES, KINGS], [], seed=11)

    assert not first.exact
    assert first == second, "the same situation shows the same numbers"
    assert random.random() == expected_next, "the global RNG is untouched"
    assert first.shares[0] == pytest.approx(0.82, abs=0.04)


def test_the_estimate_is_capped_so_the_ui_never_stalls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hands = [("AH", "AD"), ("KC", "KS"), ("QH", "QD"), ("JC", "JS"), ("TH", "TD")]
    calls = 0

    def counting(cards: list[str]) -> tuple[HandCategory, tuple[int, ...]]:
        nonlocal calls
        calls += 1
        return evaluate_rank(cards)

    monkeypatch.setattr(equity, "evaluate_rank", counting)
    calculate_equity(hands, [])

    assert 0 < calls <= ESTIMATE_EVALUATIONS


def test_invalid_hands_are_rejected() -> None:
    with pytest.raises(ValueError):
        calculate_equity([ACES], [])

    with pytest.raises(ValueError):
        calculate_equity([ACES, ("AH", "KS")], [])
