"""Hand ranges: the grid of starting hands, notation and presets."""

import pytest

from backend.application.equity import EquityCalculator, calculate_equity
from backend.application.ranges import (
    ALL_LABELS,
    ANY_TWO,
    PRESET_RANGES,
    TOTAL_COMBOS,
    HandRange,
    grid_label,
    label_combos,
    parse_range,
    range_notation,
)


def test_the_grid_holds_the_169_starting_hands() -> None:
    assert len(ALL_LABELS) == len(set(ALL_LABELS)) == 169
    assert grid_label(0, 0) == "AA"
    assert grid_label(0, 1) == "AKs", "suited above the diagonal"
    assert grid_label(1, 0) == "AKo", "offsuit below"
    assert grid_label(12, 12) == "22"
    assert sum(len(label_combos(label)) for label in ALL_LABELS) == TOTAL_COMBOS


def test_combinations_of_each_kind_of_hand() -> None:
    assert len(label_combos("QQ")) == 6
    assert label_combos("AKs") == (
        ("AC", "KC"),
        ("AD", "KD"),
        ("AH", "KH"),
        ("AS", "KS"),
    )
    assert len(label_combos("AKo")) == 12
    assert all(a[1] != b[1] for a, b in label_combos("AKo"))


@pytest.mark.parametrize(
    ("text", "labels"),
    [
        ("QQ+", {"QQ", "KK", "AA"}),
        ("A9s+", {"A9s", "ATs", "AJs", "AQs", "AKs"}),
        ("KTo+", {"KTo", "KJo", "KQo"}),
        ("AK", {"AKs", "AKo"}),
        ("KJ+", {"KJs", "KJo", "KQs", "KQo"}),
        ("22-44", {"22", "33", "44"}),
        ("K9s-K7s", {"K9s", "K8s", "K7s"}),
        ("ak, 109s", {"AKs", "AKo", "T9s"}),
        ("", set()),
    ],
)
def test_range_notation_is_read(text: str, labels: set[str]) -> None:
    assert parse_range(text) == labels


@pytest.mark.parametrize("text", ["ZZ", "AAs", "AK9", "K9s-Q7s", "AsKs"])
def test_wrong_notation_is_refused(text: str) -> None:
    with pytest.raises(ValueError):
        parse_range(text)


def test_a_range_is_written_in_the_shortest_notation() -> None:
    labels = parse_range("AA KK QQ 44 33 22 AKs AQs AJs K9s K8s K7s AKo")

    assert range_notation(labels) == "QQ+, 44-22, AJs+, K9s-K7s, AKo"


@pytest.mark.parametrize("name", list(PRESET_RANGES))
def test_every_preset_reads_and_writes_back(name: str) -> None:
    hand_range = HandRange.parse(PRESET_RANGES[name])

    assert hand_range.labels
    assert HandRange.parse(hand_range.notation) == hand_range


def test_preset_sizes_are_those_of_usual_charts() -> None:
    share = {name: HandRange.parse(text).share for name, text in PRESET_RANGES.items()}

    assert share["UTG open"] < share["HJ open"] < share["CO open"] < share["BTN open"]
    assert 0.4 < share["BTN open"] < 0.55
    assert share["BB vs BTN open — 3-bet"] < 0.1
    assert share["Any two"] == 1.0
    assert ANY_TWO.combo_count == TOTAL_COMBOS


# --- Equity against ranges ---------------------------------------------------------


def test_a_range_is_the_average_of_its_combinations() -> None:
    """Every combination counts the same: AA against KK is the mean of AA
    against each of the six kings."""
    board = ["2C", "7D", "9H"]
    calculator = EquityCalculator([("AH", "AD"), HandRange.parse("KK")], board)
    calculator.run(10**6)
    singles = [
        calculate_equity([("AH", "AD"), combo], board).shares[0]
        for combo in label_combos("KK")
    ]

    assert calculator.exact
    assert calculator.total_boards == 6 * 990
    assert calculator.result().equity[0] == pytest.approx(sum(singles) / 6)


def test_cards_in_play_remove_combinations_from_a_range() -> None:
    calculator = EquityCalculator([("KH", "KD"), HandRange.parse("KK, AA")], ["KC"])

    assert calculator.exact is False
    assert calculator._choices[0] == list(label_combos("AA")), "no king left"


def test_ranges_against_ranges_are_estimated() -> None:
    calculator = EquityCalculator(
        [HandRange.parse("QQ+"), HandRange.parse("AKs, AKo")], seed=3
    )
    calculator.run(20_000)
    result = calculator.result()

    assert not result.exact
    assert sum(result.equity) == pytest.approx(1)
    # Per AK combination: 3 AA (93%), 3 KK (70%) and 6 QQ (56%) are left.
    assert result.equity[0] == pytest.approx(0.688, abs=0.015)


def test_ranges_that_cannot_fit_together_are_refused() -> None:
    with pytest.raises(ValueError, match="no combination left together"):
        EquityCalculator(
            [("AH", "AD"), HandRange.parse("AA"), HandRange.parse("AA")], seed=1
        )


def test_a_blocked_range_is_refused() -> None:
    with pytest.raises(ValueError, match="Hand 2: no combination"):
        EquityCalculator([("AH", "AD"), HandRange.parse("AA")], ["AS", "AC"])
