"""The equity calculator: known and random hands on any board."""

import random

import pytest

from backend.application.equity import EquityCalculator, calculate_equity

ACES = ("AH", "AD")
KINGS = ("KC", "KS")
FLOP = ("2C", "7D", "9H")


def test_every_board_is_counted_on_the_flop() -> None:
    calculator = EquityCalculator([ACES, KINGS], FLOP)

    assert calculator.exact
    assert calculator.total_boards == 990  # 45 cards, 2 to come.
    assert calculator.run(10_000) == 990
    assert calculator.finished
    result = calculator.result()
    assert result.equity == calculate_equity([ACES, KINGS], list(FLOP)).shares
    assert result.margins is None
    assert result.wins[0] + result.wins[1] + result.ties[0] == pytest.approx(1)


def test_an_exact_count_can_be_done_in_steps() -> None:
    whole = EquityCalculator([ACES, KINGS], FLOP)
    whole.run(990)
    steps = EquityCalculator([ACES, KINGS], FLOP)

    while not steps.finished:
        steps.run(100)

    assert steps.result() == whole.result()


def test_a_split_board_is_a_tie() -> None:
    board = ("TC", "JD", "QH", "KD", "AS")  # Broadway on the board.
    calculator = EquityCalculator([("2C", "3C"), ("4D", "5D")], board)
    calculator.run(1)
    result = calculator.result()

    assert result.equity == (0.5, 0.5)
    assert result.ties == (1.0, 1.0)
    assert result.wins == (0.0, 0.0)


def test_known_hands_before_the_flop_are_estimated() -> None:
    calculator = EquityCalculator([ACES, KINGS], seed=3)

    assert not calculator.exact and calculator.total_boards is None
    calculator.run(20_000)
    result = calculator.result()

    assert result.equity[0] == pytest.approx(0.82, abs=0.015)
    assert result.margins is not None
    assert result.margins[0] < 0.01


def test_aces_against_a_random_hand() -> None:
    calculator = EquityCalculator([ACES, None], seed=8)
    calculator.run(20_000)
    result = calculator.result()

    assert result.equity[0] == pytest.approx(0.852, abs=0.015)
    assert sum(result.equity) == pytest.approx(1)


def test_random_hands_against_each_other_share_the_pot() -> None:
    calculator = EquityCalculator([None, None, None], seed=2)
    calculator.run(9_000)
    result = calculator.result()

    assert sum(result.equity) == pytest.approx(1)
    assert all(share == pytest.approx(1 / 3, abs=0.03) for share in result.equity)


def test_the_margin_shrinks_with_more_boards() -> None:
    calculator = EquityCalculator([ACES, None], seed=4)
    calculator.run(500)
    early = calculator.result().margins
    calculator.run(20_000)
    late = calculator.result().margins

    assert early is not None and late is not None
    assert late[0] < early[0] / 4


def test_the_same_seed_gives_the_same_numbers_and_keeps_the_global_rng() -> None:
    random.seed(1)
    expected = random.random()
    random.seed(1)

    first = EquityCalculator([ACES, None], ("2C", "7D", "9H"), seed=6)
    second = EquityCalculator([ACES, None], ("2C", "7D", "9H"), seed=6)
    first.run(2_000)
    second.run(2_000)

    assert first.result() == second.result()
    assert random.random() == expected


@pytest.mark.parametrize(
    ("hands", "board", "message"),
    [
        ([ACES], (), "2 to 6 hands"),
        ([ACES, KINGS, None, None, None, None, None], (), "2 to 6 hands"),
        ([("AH", "AD", "AC"), KINGS], (), "two cards"),
        ([ACES, ("AH", "KS")], (), "twice"),
        ([ACES, KINGS], ("AD",), "twice"),
        ([ACES, ("ZZ", "KS")], (), "Unknown card"),
        ([ACES, KINGS], ("2C", "3C", "4C", "5C", "6C", "7C"), "five cards"),
    ],
)
def test_invalid_input_is_rejected(
    hands: list[tuple[str, ...] | None], board: tuple[str, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        EquityCalculator(hands, board)


def test_there_is_no_result_before_a_board_is_counted() -> None:
    with pytest.raises(RuntimeError):
        EquityCalculator([ACES, KINGS], FLOP).result()
