from PySide6.QtWidgets import QApplication

from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import ActionType
from frontend.components.action_panel import ActionPanel

FACING_A_BET = (
    LegalAction(type=ActionType.FOLD),
    LegalAction(type=ActionType.CALL, amount=20),
    LegalAction(type=ActionType.RAISE, min_amount=40, max_amount=500),
    LegalAction(type=ActionType.ALL_IN, amount=500),
)

CHECKED_TO = (
    LegalAction(type=ActionType.FOLD),
    LegalAction(type=ActionType.CHECK),
    LegalAction(type=ActionType.RAISE, min_amount=10, max_amount=500),
    LegalAction(type=ActionType.ALL_IN, amount=500),
)


def make_panel(legal_actions: tuple[LegalAction, ...], **state: int) -> ActionPanel:
    panel = ActionPanel()
    values = {"pot": 50, "current_bet": 20, "player_bet": 0} | state
    panel.set_legal_actions(legal_actions, **values)

    return panel


def collect_actions(panel: ActionPanel) -> list[Action]:
    actions: list[Action] = []
    panel.action_chosen.connect(actions.append)

    return actions


def test_panel_is_disabled_without_legal_actions(qapp: QApplication) -> None:
    panel = ActionPanel()

    assert not panel.fold_button.isEnabled()
    assert not panel.call_button.isEnabled()
    assert not panel.raise_button.isEnabled()
    assert not panel.amount_slider.isEnabled()


def test_panel_exposes_call_and_raise_when_facing_a_bet(qapp: QApplication) -> None:
    panel = make_panel(FACING_A_BET)

    assert panel.fold_button.isEnabled()
    assert panel.call_button.text() == "Call 20"
    assert panel.raise_button.text() == "Raise to 40"
    assert panel.amount_spin.minimum() == 40
    assert panel.amount_spin.maximum() == 500


def test_panel_exposes_check_and_bet_when_checked_to(qapp: QApplication) -> None:
    panel = make_panel(CHECKED_TO, current_bet=0)

    assert panel.call_button.text() == "Check"
    assert panel.raise_button.text() == "Bet 10"


def test_buttons_emit_the_matching_actions(qapp: QApplication) -> None:
    panel = make_panel(FACING_A_BET)
    actions = collect_actions(panel)

    panel.fold_button.click()
    panel.call_button.click()
    panel.amount_spin.setValue(120)
    panel.raise_button.click()

    assert actions == [
        Action(type=ActionType.FOLD),
        Action(type=ActionType.CALL),
        Action(type=ActionType.RAISE, amount=120),
    ]


def test_check_button_emits_check(qapp: QApplication) -> None:
    panel = make_panel(CHECKED_TO, current_bet=0)
    actions = collect_actions(panel)

    panel.call_button.click()

    assert actions == [Action(type=ActionType.CHECK)]


def test_slider_and_spin_box_stay_in_sync(qapp: QApplication) -> None:
    panel = make_panel(FACING_A_BET)

    panel.amount_slider.setValue(200)

    assert panel.amount_spin.value() == 200
    assert panel.raise_button.text() == "Raise to 200"

    panel.amount_spin.setValue(500)

    assert panel.amount_slider.value() == 500
    assert panel.raise_button.text() == "All-in 500"


def test_presets_size_the_raise_within_the_legal_range(qapp: QApplication) -> None:
    panel = make_panel(FACING_A_BET, pot=50, current_bet=20, player_bet=0)

    # Calling 20 makes the pot 70: a pot-sized raise is to 20 + 70.
    panel.preset_buttons["Pot"].click()
    assert panel.amount_spin.value() == 90

    panel.preset_buttons["1/2 Pot"].click()
    assert panel.amount_spin.value() == 55

    panel.preset_buttons["Max"].click()
    assert panel.amount_spin.value() == 500

    panel.preset_buttons["Min"].click()
    assert panel.amount_spin.value() == 40


def test_preset_below_the_minimum_raise_is_clamped(qapp: QApplication) -> None:
    panel = make_panel(FACING_A_BET, pot=10, current_bet=20, player_bet=0)

    panel.preset_buttons["1/2 Pot"].click()

    assert panel.amount_spin.value() == 40


def test_short_stack_can_only_go_all_in(qapp: QApplication) -> None:
    legal_actions = (
        LegalAction(type=ActionType.FOLD),
        LegalAction(type=ActionType.CALL, amount=20),
        LegalAction(type=ActionType.ALL_IN, amount=30),
    )
    panel = make_panel(legal_actions)
    actions = collect_actions(panel)

    assert panel.raise_button.text() == "All-in 30"
    assert not panel.amount_slider.isEnabled()

    panel.raise_button.click()

    assert actions == [Action(type=ActionType.ALL_IN)]


def test_raise_is_disabled_when_only_call_or_fold_is_legal(qapp: QApplication) -> None:
    legal_actions = (
        LegalAction(type=ActionType.FOLD),
        LegalAction(type=ActionType.CALL, amount=20),
    )
    panel = make_panel(legal_actions)

    assert panel.call_button.isEnabled()
    assert not panel.raise_button.isEnabled()
    assert not panel.amount_spin.isEnabled()
