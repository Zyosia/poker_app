import pytest

from backend.game.actions import (
    call,
    can_check,
    check,
    fold,
    get_call_amount,
    get_minimum_raise_to,
    post_big_blind,
    post_small_blind,
    put_chips_in_pot,
    raise_bet,
)
from backend.game.models import Hand, Player, Table

# ============================================================
# Helpers
# ============================================================


def make_hand(*players: Player) -> Hand:
    """Create a minimal hand for action tests."""

    table = Table(
        players=list(players),
    )

    return Hand(
        table=table,
    )


def make_player(
    name: str = "Alice",
    stack: int = 100,
) -> Player:
    """Create a player with a configurable stack."""

    return Player(
        name=name,
        stack=stack,
    )


# ============================================================
# put_chips_in_pot
# ============================================================


def test_put_chips_in_pot_moves_chips_from_stack_to_pot() -> None:
    player = make_player(stack=100)
    hand = make_hand(player)

    amount = put_chips_in_pot(
        player=player,
        hand=hand,
        amount=30,
    )

    assert amount == 30
    assert player.stack == 70
    assert player.current_bet == 30
    assert player.total_contribution == 30
    assert hand.pot == 30


def test_put_chips_in_pot_accumulates_contributions() -> None:
    player = make_player(stack=100)
    hand = make_hand(player)

    put_chips_in_pot(
        player=player,
        hand=hand,
        amount=30,
    )

    put_chips_in_pot(
        player=player,
        hand=hand,
        amount=20,
    )

    assert player.stack == 50
    assert player.current_bet == 50
    assert player.total_contribution == 50
    assert hand.pot == 50


def test_put_chips_in_pot_caps_amount_at_stack() -> None:
    player = make_player(stack=50)
    hand = make_hand(player)

    amount = put_chips_in_pot(
        player=player,
        hand=hand,
        amount=100,
    )

    assert amount == 50
    assert player.stack == 0
    assert player.current_bet == 50
    assert player.total_contribution == 50
    assert hand.pot == 50


def test_put_chips_in_pot_sets_all_in_when_stack_reaches_zero() -> None:
    player = make_player(stack=50)
    hand = make_hand(player)

    put_chips_in_pot(
        player=player,
        hand=hand,
        amount=50,
    )

    assert player.stack == 0
    assert player.all_in is True


def test_put_chips_in_pot_does_not_set_all_in_when_stack_remains() -> None:
    player = make_player(stack=50)
    hand = make_hand(player)

    put_chips_in_pot(
        player=player,
        hand=hand,
        amount=40,
    )

    assert player.stack == 10
    assert player.all_in is False


def test_put_chips_in_pot_rejects_negative_amount() -> None:
    player = make_player(stack=100)
    hand = make_hand(player)

    with pytest.raises(ValueError):
        put_chips_in_pot(
            player=player,
            hand=hand,
            amount=-1,
        )


def test_put_chips_in_pot_zero_amount_changes_nothing() -> None:
    player = make_player(stack=100)
    hand = make_hand(player)

    amount = put_chips_in_pot(
        player=player,
        hand=hand,
        amount=0,
    )

    assert amount == 0
    assert player.stack == 100
    assert player.current_bet == 0
    assert player.total_contribution == 0
    assert hand.pot == 0
    assert player.all_in is False


# ============================================================
# Blinds
# ============================================================


def test_post_small_blind() -> None:
    player = make_player(stack=100)
    hand = make_hand(player)

    amount = post_small_blind(
        player=player,
        hand=hand,
        amount=5,
    )

    assert amount == 5
    assert player.stack == 95
    assert player.current_bet == 5
    assert player.total_contribution == 5
    assert hand.pot == 5


def test_post_big_blind_updates_current_bet() -> None:
    player = make_player(stack=100)
    hand = make_hand(player)

    amount = post_big_blind(
        player=player,
        hand=hand,
        amount=10,
    )

    assert amount == 10
    assert player.stack == 90
    assert player.current_bet == 10
    assert player.total_contribution == 10
    assert hand.pot == 10
    assert hand.current_bet == 10
    assert hand.last_raise_size == 10


def test_short_big_blind_is_capped_at_stack() -> None:
    player = make_player(stack=5)
    hand = make_hand(player)

    amount = post_big_blind(
        player=player,
        hand=hand,
        amount=10,
    )

    assert amount == 5
    assert player.stack == 0
    assert player.current_bet == 5
    assert player.total_contribution == 5
    assert player.all_in is True
    assert hand.pot == 5
    assert hand.current_bet == 5
    assert hand.last_raise_size == 5


# ============================================================
# Fold
# ============================================================


def test_fold_marks_player_as_folded() -> None:
    player = make_player()

    fold(player)

    assert player.folded is True
    assert player.acted_this_round is True


def test_fold_does_not_change_stack_or_contribution() -> None:
    player = make_player(stack=100)
    hand = make_hand(player)

    put_chips_in_pot(
        player=player,
        hand=hand,
        amount=20,
    )

    fold(player)

    assert player.stack == 80
    assert player.current_bet == 20
    assert player.total_contribution == 20
    assert hand.pot == 20


# ============================================================
# Check
# ============================================================


def test_can_check_when_player_matches_current_bet() -> None:
    player = make_player()
    hand = make_hand(player)

    hand.current_bet = 20
    player.current_bet = 20

    assert (
        can_check(
            player=player,
            hand=hand,
        )
        is True
    )


def test_cannot_check_when_player_is_behind_current_bet() -> None:
    player = make_player()
    hand = make_hand(player)

    hand.current_bet = 20
    player.current_bet = 10

    assert (
        can_check(
            player=player,
            hand=hand,
        )
        is False
    )


def test_check_marks_player_as_acted() -> None:
    player = make_player()
    hand = make_hand(player)

    hand.current_bet = 20
    player.current_bet = 20

    check(
        player=player,
        hand=hand,
    )

    assert player.acted_this_round is True


def test_check_rejects_player_who_has_not_matched_bet() -> None:
    player = make_player()
    hand = make_hand(player)

    hand.current_bet = 20
    player.current_bet = 10

    with pytest.raises(ValueError):
        check(
            player=player,
            hand=hand,
        )

    assert player.acted_this_round is False


# ============================================================
# Call
# ============================================================


def test_get_call_amount_returns_difference() -> None:
    player = make_player()
    hand = make_hand(player)

    player.current_bet = 10
    hand.current_bet = 30

    assert (
        get_call_amount(
            player=player,
            hand=hand,
        )
        == 20
    )


def test_get_call_amount_returns_zero_when_already_matched() -> None:
    player = make_player()
    hand = make_hand(player)

    player.current_bet = 30
    hand.current_bet = 30

    assert (
        get_call_amount(
            player=player,
            hand=hand,
        )
        == 0
    )


def test_get_call_amount_never_returns_negative() -> None:
    player = make_player()
    hand = make_hand(player)

    player.current_bet = 40
    hand.current_bet = 30

    assert (
        get_call_amount(
            player=player,
            hand=hand,
        )
        == 0
    )


def test_call_moves_required_chips() -> None:
    player = make_player(stack=100)
    hand = make_hand(player)

    player.current_bet = 10
    hand.current_bet = 30

    amount = call(
        player=player,
        hand=hand,
    )

    assert amount == 20
    assert player.stack == 80
    assert player.current_bet == 30
    assert player.total_contribution == 20
    assert hand.pot == 20
    assert player.acted_this_round is True


def test_call_can_result_in_short_all_in() -> None:
    player = make_player(stack=15)
    hand = make_hand(player)

    player.current_bet = 10
    hand.current_bet = 30

    amount = call(
        player=player,
        hand=hand,
    )

    assert amount == 15
    assert player.stack == 0
    assert player.current_bet == 25
    assert player.all_in is True
    assert player.acted_this_round is True
    assert hand.pot == 15


def test_call_does_not_add_chips_when_already_matched() -> None:
    player = make_player(stack=100)
    hand = make_hand(player)

    player.current_bet = 30
    hand.current_bet = 30

    amount = call(
        player=player,
        hand=hand,
    )

    assert amount == 0
    assert player.stack == 100
    assert player.current_bet == 30
    assert player.total_contribution == 0
    assert hand.pot == 0
    assert player.acted_this_round is True


# ============================================================
# Minimum raise
# ============================================================


def test_get_minimum_raise_to() -> None:
    hand = make_hand()

    hand.current_bet = 20
    hand.last_raise_size = 10

    assert get_minimum_raise_to(hand) == 30


def test_minimum_raise_is_current_bet_plus_last_raise() -> None:
    hand = make_hand()

    hand.current_bet = 50
    hand.last_raise_size = 25

    assert get_minimum_raise_to(hand) == 75


def test_minimum_raise_is_zero_when_no_current_bet() -> None:
    hand = make_hand()

    hand.current_bet = 0
    hand.last_raise_size = 0

    assert get_minimum_raise_to(hand) == 0


# ============================================================
# Raise
# ============================================================


def test_raise_bet_moves_only_incremental_chips() -> None:
    player = make_player(stack=100)
    hand = make_hand(player)

    player.current_bet = 20
    hand.current_bet = 20
    hand.last_raise_size = 10

    new_bet = raise_bet(
        player=player,
        hand=hand,
        raise_to=40,
    )

    assert new_bet == 40
    assert player.stack == 80
    assert player.current_bet == 40
    assert player.total_contribution == 20
    assert hand.pot == 20
    assert hand.current_bet == 40
    assert hand.last_raise_size == 20
    assert hand.last_raiser is player
    assert player.acted_this_round is True


def test_raise_requires_amount_above_current_bet() -> None:
    player = make_player(stack=100)
    hand = make_hand(player)

    hand.current_bet = 20
    hand.last_raise_size = 10
    player.current_bet = 20

    with pytest.raises(ValueError):
        raise_bet(
            player=player,
            hand=hand,
            raise_to=20,
        )


def test_raise_requires_minimum_raise_size() -> None:
    player = make_player(stack=100)
    hand = make_hand(player)

    hand.current_bet = 20
    hand.last_raise_size = 10
    player.current_bet = 20

    with pytest.raises(ValueError):
        raise_bet(
            player=player,
            hand=hand,
            raise_to=25,
        )


def test_raise_accepts_exact_minimum_raise() -> None:
    player = make_player(stack=100)
    hand = make_hand(player)

    hand.current_bet = 20
    hand.last_raise_size = 10
    player.current_bet = 20

    new_bet = raise_bet(
        player=player,
        hand=hand,
        raise_to=30,
    )

    assert new_bet == 30
    assert player.stack == 90
    assert player.current_bet == 30
    assert hand.current_bet == 30
    assert hand.last_raise_size == 10
    assert hand.last_raiser is player


def test_raise_rejects_when_stack_is_insufficient() -> None:
    player = make_player(stack=5)
    hand = make_hand(player)

    hand.current_bet = 20
    hand.last_raise_size = 10
    player.current_bet = 20

    with pytest.raises(ValueError):
        raise_bet(
            player=player,
            hand=hand,
            raise_to=30,
        )

    assert player.stack == 5
    assert player.current_bet == 20
    assert hand.current_bet == 20
    assert hand.pot == 0


def test_raise_updates_last_raiser() -> None:
    player = make_player()
    hand = make_hand(player)

    hand.current_bet = 20
    hand.last_raise_size = 10
    player.current_bet = 20

    raise_bet(
        player=player,
        hand=hand,
        raise_to=40,
    )

    assert hand.last_raiser is player


def test_raise_marks_player_as_acted() -> None:
    player = make_player()
    hand = make_hand(player)

    hand.current_bet = 20
    hand.last_raise_size = 10
    player.current_bet = 20

    raise_bet(
        player=player,
        hand=hand,
        raise_to=40,
    )

    assert player.acted_this_round is True


# ============================================================
# All-in through raise_bet
# ============================================================


def test_raise_to_exact_stack_results_in_all_in() -> None:
    player = make_player(stack=30)
    hand = make_hand(player)

    player.current_bet = 20
    hand.current_bet = 20
    hand.last_raise_size = 10

    raise_bet(
        player=player,
        hand=hand,
        raise_to=50,
    )

    assert player.stack == 0
    assert player.current_bet == 50
    assert player.all_in is True
    assert hand.current_bet == 50


def test_raise_does_not_allow_amount_above_stack() -> None:
    player = make_player(stack=30)
    hand = make_hand(player)

    player.current_bet = 20
    hand.current_bet = 20
    hand.last_raise_size = 10

    with pytest.raises(ValueError):
        raise_bet(
            player=player,
            hand=hand,
            raise_to=51,
        )

    assert player.stack == 30
    assert player.current_bet == 20
    assert hand.current_bet == 20
