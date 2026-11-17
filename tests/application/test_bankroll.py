"""The bankroll: money movements, adjustments, saving and crash recovery."""

import ast
from datetime import datetime
from pathlib import Path

import pytest

from backend.application.bankroll import (
    DEFAULT_BALANCE,
    RELOAD_THRESHOLD,
    Bankroll,
    GameAccount,
    GameMode,
    InsufficientFundsError,
    TransactionType,
    bankroll_hint,
)
from backend.application.profile import ProfileStore

PROJECT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path: Path) -> ProfileStore:
    return ProfileStore(tmp_path / "profile.json")


def account(store: ProfileStore, mode: GameMode, name: str = "Game") -> GameAccount:
    return GameAccount(store.bankroll, mode, name, save=store.save)


def kinds(bankroll: Bankroll) -> list[tuple[TransactionType, int]]:
    return [(t.type, t.amount) for t in bankroll.transactions]


def test_the_first_launch_starts_with_the_default_balance(store: ProfileStore) -> None:
    assert store.bankroll.balance == DEFAULT_BALANCE == 100_000
    assert store.bankroll.transactions == []
    assert store.bankroll.balance_history() == [DEFAULT_BALANCE]


# --- Money movements ------------------------------------------------------------


def test_a_cash_game_pays_its_buy_in_and_rebuys_and_cashes_out(
    store: ProfileStore,
) -> None:
    cash = account(store, GameMode.CASH, "Cash game 5/10")

    cash.start(buy_in=1000, stack=1000)
    cash.pay(TransactionType.REBUY, 1000)
    cash.update_stack(2350)
    cash.cash_out(2350)

    bankroll = store.bankroll
    assert kinds(bankroll) == [
        (TransactionType.BUY_IN, -1000),
        (TransactionType.REBUY, -1000),
        (TransactionType.CASH_OUT, 2350),
    ]
    assert bankroll.balance == 100_350
    assert [t.balance_after for t in bankroll.transactions] == [99_000, 98_000, 100_350]
    assert all(t.mode == GameMode.CASH for t in bankroll.transactions)
    assert len({t.game_id for t in bankroll.transactions}) == 1
    assert bankroll.open_games == []
    assert bankroll.net_result(GameMode.CASH) == 350

    cash.cash_out(5000)  # A second cash-out is ignored.
    assert bankroll.balance == 100_350


def test_a_tournament_pays_buy_in_rebuy_and_add_on_and_credits_the_prize(
    store: ProfileStore,
) -> None:
    tournament = account(store, GameMode.TOURNAMENT, "Tournament (Turbo)")

    tournament.start(buy_in=1000)
    tournament.pay(TransactionType.REBUY, 1000)
    tournament.pay(TransactionType.ADD_ON, 1000)
    tournament.finish(prize=4200)

    assert kinds(store.bankroll) == [
        (TransactionType.BUY_IN, -1000),
        (TransactionType.REBUY, -1000),
        (TransactionType.ADD_ON, -1000),
        (TransactionType.PRIZE, 4200),
    ]
    assert store.bankroll.balance == 101_200
    assert store.bankroll.net_result(GameMode.TOURNAMENT) == 1200


def test_a_tournament_without_a_prize_records_no_payout(store: ProfileStore) -> None:
    tournament = account(store, GameMode.TOURNAMENT)
    tournament.start(buy_in=500)
    tournament.finish(prize=0)

    assert kinds(store.bankroll) == [(TransactionType.BUY_IN, -500)]
    assert store.bankroll.open_games == []


@pytest.mark.parametrize("multiplier", [2, 1000])
def test_a_spin_and_go_pays_its_buy_in_and_credits_its_prize(
    store: ProfileStore, multiplier: int
) -> None:
    spin = account(store, GameMode.SPIN, "Spin & Go")
    spin.start(buy_in=1000)
    spin.finish(prize=1000 * multiplier)

    assert store.bankroll.balance == DEFAULT_BALANCE - 1000 + 1000 * multiplier
    assert store.bankroll.net_result(GameMode.SPIN) == 1000 * (multiplier - 1)


def test_a_freeroll_costs_nothing(store: ProfileStore) -> None:
    freeroll = account(store, GameMode.TOURNAMENT)
    freeroll.start(buy_in=0)

    assert store.bankroll.balance == DEFAULT_BALANCE


def test_a_buy_in_larger_than_the_balance_is_refused(store: ProfileStore) -> None:
    store.bankroll.set_balance(800)
    cash = account(store, GameMode.CASH)

    with pytest.raises(InsufficientFundsError):
        cash.start(buy_in=1000, stack=1000)

    assert store.bankroll.balance == 800
    assert store.bankroll.open_games == []
    assert not cash.can_pay(1000)
    assert store.bankroll.can_afford(800)


def test_every_change_is_saved_at_once(store: ProfileStore) -> None:
    cash = account(store, GameMode.CASH)
    cash.start(buy_in=1000, stack=1000)

    reloaded = ProfileStore(store.path)
    assert reloaded.bankroll.balance == 99_000
    assert [game.game_id for game in reloaded.bankroll.open_games] == [cash.game_id]


# --- Adjustments ----------------------------------------------------------------


def test_set_reset_and_reload_are_recorded_as_adjustments(store: ProfileStore) -> None:
    bankroll = store.bankroll

    bankroll.set_balance(250_000)
    assert bankroll.balance == 250_000
    bankroll.reset()
    assert bankroll.balance == DEFAULT_BALANCE

    with pytest.raises(ValueError):
        bankroll.reload()  # Not broke.

    bankroll.set_balance(RELOAD_THRESHOLD - 1)
    assert bankroll.can_reload
    bankroll.reload()

    assert bankroll.balance == DEFAULT_BALANCE
    assert [(t.type, t.amount, t.mode) for t in bankroll.transactions] == [
        (TransactionType.ADJUSTMENT, 150_000, None),
        (TransactionType.ADJUSTMENT, -150_000, None),
        (TransactionType.ADJUSTMENT, -100_000 + RELOAD_THRESHOLD - 1, None),
        (TransactionType.ADJUSTMENT, 100_000 - RELOAD_THRESHOLD + 1, None),
    ]
    assert bankroll.net_result() == 0, "adjustments are not results"

    with pytest.raises(ValueError):
        bankroll.set_balance(-1)


def test_the_history_follows_the_balance(store: ProfileStore) -> None:
    bankroll = store.bankroll
    bankroll.now = lambda: datetime(2026, 11, 17, 20, 30, 5)
    account(store, GameMode.SPIN).start(buy_in=1000)

    assert bankroll.balance_history() == [100_000, 99_000]
    assert bankroll.transactions[0].time == "2026-11-17T20:30:05"


def test_bankroll_hints_follow_the_rules_of_thumb() -> None:
    assert bankroll_hint(GameMode.CASH, 1000, 20_000) is None
    assert bankroll_hint(GameMode.CASH, 1000, 19_999) is not None
    assert bankroll_hint(GameMode.TOURNAMENT, 1000, 50_000) is None
    hint = bankroll_hint(GameMode.SPIN, 5000, 100_000)
    assert hint is not None and "20 buy-ins" in hint and "50" in hint
    assert bankroll_hint(GameMode.TOURNAMENT, 0, 10) is None  # Freeroll.


# --- Saving and recovery --------------------------------------------------------


def test_a_damaged_profile_keeps_the_balance_from_the_backup(
    store: ProfileStore,
) -> None:
    account(store, GameMode.SPIN).start(buy_in=1000)
    store.save()  # The backup now holds the same balance.
    assert store.path is not None
    store.path.write_text('{"format_version": 1, "bankroll": {"balance": "x"}}')

    restored = ProfileStore(store.path)

    assert restored.bankroll.balance == 99_000
    assert restored.warning is not None


def test_a_crash_in_a_cash_game_cashes_out_the_last_saved_stack(
    store: ProfileStore,
) -> None:
    cash = account(store, GameMode.CASH, "Cash game 5/10")
    cash.start(buy_in=1000, stack=1000)
    cash.update_stack(740)
    # The application closes here, without cashing out.

    next_launch = ProfileStore(store.path)
    [recovered] = next_launch.bankroll.recover_open_games()

    assert recovered.type == TransactionType.CASH_OUT
    assert recovered.amount == 740
    assert "closed during the session" in recovered.description
    assert next_launch.bankroll.balance == 99_740
    assert next_launch.bankroll.open_games == []
    assert next_launch.bankroll.recover_open_games() == []


def test_closing_during_a_tournament_forfeits_it(store: ProfileStore) -> None:
    account(store, GameMode.TOURNAMENT, "Tournament (Turbo)").start(buy_in=1000)

    next_launch = ProfileStore(store.path)
    [recovered] = next_launch.bankroll.recover_open_games()

    assert recovered.type == TransactionType.FORFEIT
    assert recovered.amount == 0
    assert next_launch.bankroll.balance == 99_000


# --- Several tables at once ----------------------------------------------------


def test_several_games_are_open_at_once_each_with_its_own_account(
    store: ProfileStore,
) -> None:
    first = account(store, GameMode.CASH, "Cash game 5/10")
    first.start(buy_in=1000, stack=1000)
    second = account(store, GameMode.CASH, "Cash game 25/50")
    second.start(buy_in=5000, stack=5000)
    spin = account(store, GameMode.SPIN, "Spin & Go")
    spin.start(buy_in=500)

    assert len({first.game_id, second.game_id, spin.game_id}) == 3
    assert store.bankroll.balance == 93_500

    second.update_stack(6200)
    first.cash_out(800)

    assert [game.game_id for game in store.bankroll.open_games] == [
        second.game_id,
        spin.game_id,
    ]
    open_second = store.bankroll.open_game(second.game_id)
    assert open_second is not None and open_second.stack == 6200
    assert store.bankroll.balance == 94_300


def test_a_crash_with_several_tables_open_settles_each_of_them(
    store: ProfileStore,
) -> None:
    cash = account(store, GameMode.CASH, "Cash game 5/10")
    cash.start(buy_in=1000, stack=1000)
    cash.update_stack(1300)
    account(store, GameMode.TOURNAMENT, "Tournament (Turbo)").start(buy_in=2000)

    next_launch = ProfileStore(store.path)
    recovered = next_launch.bankroll.recover_open_games()

    assert [(t.type, t.amount) for t in recovered] == [
        (TransactionType.CASH_OUT, 1300),
        (TransactionType.FORFEIT, 0),
    ]
    assert next_launch.bankroll.balance == 100_000 - 1000 - 2000 + 1300
    assert next_launch.bankroll.open_games == []


def test_tables_opened_at_the_same_instant_get_distinct_ids(
    store: ProfileStore,
) -> None:
    store.bankroll.now = lambda: datetime(2026, 11, 17, 12, 0, 0)
    ids = []

    for _ in range(3):
        cash = account(store, GameMode.CASH)
        cash.start(buy_in=100, stack=100)
        ids.append(cash.game_id)

    assert len(set(ids)) == 3


def test_a_profile_saved_before_multi_tabling_keeps_its_open_game() -> None:
    data = Bankroll().to_dict()
    del data["open_games"]
    data["open_game"] = {
        "game_id": "cash_1",
        "mode": "cash",
        "description": "Cash game 5/10",
        "stack": 900,
    }

    bankroll = Bankroll.from_dict(data)

    assert [(game.game_id, game.stack) for game in bankroll.open_games] == [
        ("cash_1", 900)
    ]


def test_leaving_a_running_tournament_forfeits_it(store: ProfileStore) -> None:
    tournament = account(store, GameMode.TOURNAMENT)
    tournament.start(buy_in=1000)
    tournament.forfeit()
    tournament.finish(prize=5000)  # Too late: the account is closed.

    assert kinds(store.bankroll) == [
        (TransactionType.BUY_IN, -1000),
        (TransactionType.FORFEIT, 0),
    ]
    assert store.bankroll.open_games == []


def test_the_simulations_never_touch_the_bankroll() -> None:
    """Bot Arena and the CLI import neither the bankroll nor the profile."""
    for path in (PROJECT / "backend" / "simulation").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }

        assert not any("bankroll" in name or "profile" in name for name in imported), (
            path.name
        )
