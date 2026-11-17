"""The heads-up push/fold solver (CFR+)."""

import pytest

from backend.bots.push_fold_solver import (
    HANDS,
    Matrix,
    PushFoldStrategy,
    combo_pair_counts,
    equity_matrix,
    exploitability,
    solution_source,
    solve,
)


@pytest.fixture(scope="module")
def weights() -> Matrix:
    return combo_pair_counts()


@pytest.fixture(scope="module")
def equity() -> Matrix:
    """A coarse matrix (few boards per pair): enough to test the solver."""
    return equity_matrix(samples=4, seed=1)


def index(hand: str) -> int:
    return HANDS.index(hand)


def test_card_removal_counts_the_combinations_left(weights: Matrix) -> None:
    assert weights[index("AA")][index("AA")] == 1 * 6  # Two aces left: one pair.
    assert weights[index("AA")][index("KK")] == 36
    assert weights[index("AKs")][index("AKs")] == 12
    assert weights[index("AKo")][index("72o")] == 144


def test_equities_are_complementary(equity: Matrix) -> None:
    for i in range(0, len(HANDS), 17):
        for j in range(0, len(HANDS), 13):
            assert equity[i][j] + equity[j][i] == pytest.approx(1.0)


def test_cfr_converges_to_an_equilibrium(weights: Matrix, equity: Matrix) -> None:
    early = solve(equity, weights, stack=10, iterations=5)
    late = solve(equity, weights, stack=10, iterations=150)

    assert exploitability(late, equity, weights) < exploitability(
        early, equity, weights
    )
    assert exploitability(late, equity, weights) < 0.005
    assert late.push[index("AA")] > 0.99 and late.call[index("AA")] > 0.99
    assert late.push[index("72o")] < 0.01


def test_an_unexploitable_strategy_beats_a_bad_one(
    weights: Matrix, equity: Matrix
) -> None:
    always = PushFoldStrategy(10, push=(1.0,) * len(HANDS), call=(1.0,) * len(HANDS))
    solved = solve(equity, weights, stack=10, iterations=100)

    assert exploitability(always, equity, weights) > 10 * exploitability(
        solved, equity, weights
    )


def test_the_solution_module_is_valid_python() -> None:
    source = solution_source({1: ("22+, A2s+", "AA"), 2: ("", "KK+, AKs")})
    namespace: dict[str, object] = {}
    exec(compile(source, "heads_up_push_fold", "exec"), namespace)

    assert namespace["PUSH_FOLD_RANGES"] == {
        1: ("22+, A2s+", "AA"),
        2: ("", "KK+, AKs"),
    }
