from functools import partial
from unittest.mock import Mock

import pytest

from powerrules.engine.exceptions import ActionExecutionError, ConditionEvaluationError
from powerrules.engine.models import Rule
from powerrules.engine.rule_engine import RuleEngine
from tests.mocks import make_action, make_condition


def _make_rule(
    name: str,
    condition: Mock,
    *actions: Mock,
    enabled: bool = True,
) -> Rule:
    """Create a rule with the given (mocked) condition and actions."""
    return Rule(
        name=name,
        condition=condition,
        actions=actions,
        enabled=enabled,
    )


#########################
# Rule matching and order
#########################


def test_rule_engine_executes_action_when_condition_matches() -> None:
    condition = make_condition(True)
    action = make_action()
    rule = _make_rule("Test rule", condition, action)

    result = RuleEngine((rule,)).evaluate()

    assert result.matched_rule is rule
    condition.evaluate.assert_called_once_with()
    action.execute.assert_called_once_with()


def test_rule_engine_skips_non_matching_rule() -> None:
    condition = make_condition(False)
    action = make_action()
    rule = _make_rule("Test rule", condition, action)

    result = RuleEngine((rule,)).evaluate()

    assert result.matched_rule is None
    condition.evaluate.assert_called_once_with()
    action.execute.assert_not_called()


def test_rule_engine_accepts_any_sequence_of_rules() -> None:
    rule = _make_rule("Test rule", make_condition(True), make_action())

    assert RuleEngine([rule]).rules == (rule,)


def test_rule_engine_evaluates_rules_from_top_to_bottom() -> None:
    first_condition = make_condition(False)
    first_action = make_action()

    second_condition = make_condition(True)
    second_action = make_action()

    rules = (
        _make_rule("First test rule", first_condition, first_action),
        _make_rule("Second test rule", second_condition, second_action),
    )

    result = RuleEngine(rules).evaluate()

    assert result.matched_rule is rules[1]
    first_condition.evaluate.assert_called_once_with()
    first_action.execute.assert_not_called()
    second_condition.evaluate.assert_called_once_with()
    second_action.execute.assert_called_once_with()


def test_rule_engine_stops_after_first_matching_rule() -> None:
    first_condition = make_condition(True)
    first_action = make_action()

    second_condition = make_condition(True)
    second_action = make_action()

    rules = (
        _make_rule("First test rule", first_condition, first_action),
        _make_rule("Second test rule", second_condition, second_action),
    )

    result = RuleEngine(rules).evaluate()

    assert result.matched_rule is rules[0]
    first_action.execute.assert_called_once_with()
    # The second rule should not even be evaluated
    second_condition.evaluate.assert_not_called()
    second_action.execute.assert_not_called()


def test_rule_engine_skips_disabled_rules() -> None:
    condition = make_condition(True)
    action = make_action()
    rule = _make_rule("Disabled test rule", condition, action, enabled=False)

    result = RuleEngine((rule,)).evaluate()

    assert result.matched_rule is None
    condition.evaluate.assert_not_called()
    action.execute.assert_not_called()


def test_rule_engine_skips_disabled_rule_and_matches_next_rule() -> None:
    disabled_condition = make_condition(True)
    disabled_action = make_action()
    enabled_action = make_action()

    disabled_rule = _make_rule(
        "Disabled test rule", disabled_condition, disabled_action, enabled=False
    )
    enabled_rule = _make_rule("Enabled test rule", make_condition(True), enabled_action)

    result = RuleEngine((disabled_rule, enabled_rule)).evaluate()

    assert result.matched_rule is enabled_rule
    disabled_condition.evaluate.assert_not_called()
    disabled_action.execute.assert_not_called()
    enabled_action.execute.assert_called_once_with()


def test_rule_engine_returns_no_match_when_no_rule_matches() -> None:
    first_action = make_action()
    second_action = make_action()

    rules = (
        _make_rule("First test rule", make_condition(False), first_action),
        _make_rule("Second test rule", make_condition(False), second_action),
    )

    result = RuleEngine(rules).evaluate()

    assert result.matched_rule is None
    first_action.execute.assert_not_called()
    second_action.execute.assert_not_called()


# This should not happen in practice due to YAML validation
def test_rule_engine_returns_no_match_for_empty_rule_list() -> None:
    result = RuleEngine(()).evaluate()

    assert result.matched_rule is None
    assert result.action_triggered is False


##################
# Multiple actions
##################


def test_rule_engine_executes_all_actions_of_the_matching_rule_in_order() -> None:
    execution_order: list[str] = []
    actions = [make_action(f"Action {number}") for number in range(1, 4)]

    for action in actions:
        action.execute.side_effect = partial(execution_order.append, action.name)

    rule = _make_rule("Test rule", make_condition(True), *actions)

    RuleEngine((rule,)).evaluate()

    assert execution_order == ["Action 1", "Action 2", "Action 3"]


def test_rule_engine_only_executes_actions_of_the_matching_rule() -> None:
    first_action = make_action("First action")
    second_action = make_action("Second action")

    rules = (
        _make_rule("First test rule", make_condition(False), first_action),
        _make_rule("Second test rule", make_condition(True), second_action),
    )

    RuleEngine(rules).evaluate()

    first_action.execute.assert_not_called()
    second_action.execute.assert_called_once_with()


######################
# Error handling tests
######################


def test_rule_engine_propagates_condition_evaluation_error() -> None:
    action = make_action()

    rule = _make_rule(
        "Failing test rule",
        make_condition(error=ConditionEvaluationError("Test condition failed")),
        action,
    )

    with pytest.raises(ConditionEvaluationError, match="Test condition failed"):
        RuleEngine((rule,)).evaluate()

    action.execute.assert_not_called()


def test_rule_engine_stops_after_condition_evaluation_error() -> None:
    first_rule = _make_rule(
        "Failing test rule",
        make_condition(error=ConditionEvaluationError("Test condition failed")),
        make_action(),
    )

    second_condition = make_condition(True)
    second_action = make_action()
    second_rule = _make_rule("Second test rule", second_condition, second_action)

    with pytest.raises(ConditionEvaluationError):
        RuleEngine((first_rule, second_rule)).evaluate()

    second_condition.evaluate.assert_not_called()
    second_action.execute.assert_not_called()


def test_rule_engine_propagates_action_execution_error() -> None:
    rule = _make_rule(
        "Failing test rule",
        make_condition(True),
        make_action(error=ActionExecutionError("Test action failed")),
    )

    with pytest.raises(ActionExecutionError, match="Test action failed"):
        RuleEngine((rule,)).evaluate()


def test_rule_engine_stops_after_action_execution_error() -> None:
    first_rule = _make_rule(
        "Failing test rule",
        make_condition(True),
        make_action(error=ActionExecutionError("Test action failed")),
    )

    second_condition = make_condition(True)
    second_action = make_action()
    second_rule = _make_rule("Second test rule", second_condition, second_action)

    with pytest.raises(ActionExecutionError):
        RuleEngine((first_rule, second_rule)).evaluate()

    second_condition.evaluate.assert_not_called()
    second_action.execute.assert_not_called()


def test_rule_engine_skips_remaining_actions_after_action_execution_error() -> None:
    first_action = make_action("First action")
    failing_action = make_action(
        "Failing action", error=ActionExecutionError("Test action failed")
    )
    last_action = make_action("Last action")

    rule = _make_rule(
        "Test rule", make_condition(True), first_action, failing_action, last_action
    )

    with pytest.raises(ActionExecutionError, match="Test action failed"):
        RuleEngine((rule,)).evaluate()

    first_action.execute.assert_called_once_with()
    failing_action.execute.assert_called_once_with()
    last_action.execute.assert_not_called()


##################
# find_match tests
##################


def test_rule_engine_find_match_returns_matching_rule() -> None:
    condition = make_condition(True)
    action = make_action()
    rule = _make_rule("Test rule", condition, action)

    matched_rule = RuleEngine((rule,)).find_match()

    assert matched_rule is rule
    condition.evaluate.assert_called_once_with()
    # Only finding a match must never execute anything
    action.execute.assert_not_called()


def test_rule_engine_find_match_returns_none_when_no_rule_matches() -> None:
    rule = _make_rule("Test rule", make_condition(False), make_action())

    assert RuleEngine((rule,)).find_match() is None


def test_rule_engine_find_match_returns_first_matching_rule() -> None:
    first_rule = _make_rule("First rule", make_condition(True), make_action())
    second_condition = make_condition(True)
    second_rule = _make_rule("Second rule", second_condition, make_action())

    matched_rule = RuleEngine((first_rule, second_rule)).find_match()

    assert matched_rule is first_rule
    second_condition.evaluate.assert_not_called()


##########################################
# previous_matched_rule / action_triggered
##########################################


def test_rule_engine_evaluate_triggers_actions_on_first_match() -> None:
    action = make_action()
    rule = _make_rule("Test rule", make_condition(True), action)

    result = RuleEngine((rule,)).evaluate()

    assert result.matched_rule is rule
    assert result.action_triggered is True
    action.execute.assert_called_once_with()


def test_rule_engine_evaluate_does_not_retrigger_same_matched_rule() -> None:
    action = make_action()
    rule = _make_rule("Test rule", make_condition(True), action)
    engine = RuleEngine((rule,))

    first_result = engine.evaluate()
    second_result = engine.evaluate(previous_matched_rule=first_result.matched_rule)

    assert second_result.matched_rule is rule
    assert second_result.action_triggered is False
    # The action was only executed once, not on the second (repeated) match
    action.execute.assert_called_once_with()


def test_rule_engine_evaluate_retriggers_after_no_match_in_between() -> None:
    condition = make_condition()
    # The rule matches, stops matching and matches again (like in a polling loop)
    condition.evaluate.side_effect = [True, False, True]
    action = make_action()
    rule = _make_rule("Test rule", condition, action)
    engine = RuleEngine((rule,))

    first_result = engine.evaluate()
    second_result = engine.evaluate(previous_matched_rule=first_result.matched_rule)
    third_result = engine.evaluate(previous_matched_rule=second_result.matched_rule)

    assert first_result.action_triggered is True
    assert second_result.matched_rule is None
    assert second_result.action_triggered is False
    assert third_result.matched_rule is rule
    assert third_result.action_triggered is True
    # Triggered once on the first match and once again after the "no match" gap
    assert action.execute.call_count == 2


def test_rule_engine_evaluate_retriggers_when_matched_rule_changes() -> None:
    first_condition = make_condition()
    # The first rule matches only on the first evaluation
    first_condition.evaluate.side_effect = [True, False]
    second_condition = make_condition(True)
    first_action = make_action()
    second_action = make_action()

    first_rule = _make_rule("First rule", first_condition, first_action)
    second_rule = _make_rule("Second rule", second_condition, second_action)
    engine = RuleEngine((first_rule, second_rule))

    first_result = engine.evaluate()
    second_result = engine.evaluate(previous_matched_rule=first_result.matched_rule)

    assert first_result.matched_rule is first_rule
    assert second_result.matched_rule is second_rule
    assert second_result.action_triggered is True
    first_action.execute.assert_called_once_with()
    second_action.execute.assert_called_once_with()


def test_rule_engine_evaluate_does_not_trigger_actions_for_no_match() -> None:
    action = make_action()
    rule = _make_rule("Test rule", make_condition(False), action)

    result = RuleEngine((rule,)).evaluate()

    assert result.matched_rule is None
    assert result.action_triggered is False
    action.execute.assert_not_called()


###############
# dry_run tests
###############


def test_rule_engine_evaluate_dry_run_reports_trigger_without_executing() -> None:
    first_action = make_action("First action")
    second_action = make_action("Second action")
    rule = _make_rule("Test rule", make_condition(True), first_action, second_action)

    result = RuleEngine((rule,)).evaluate(dry_run=True)

    assert result.matched_rule is rule
    assert result.action_triggered is True
    first_action.execute.assert_not_called()
    second_action.execute.assert_not_called()


def test_rule_engine_evaluate_dry_run_does_not_retrigger_same_matched_rule() -> None:
    action = make_action()
    rule = _make_rule("Test rule", make_condition(True), action)
    engine = RuleEngine((rule,))

    first_result = engine.evaluate(dry_run=True)
    second_result = engine.evaluate(
        previous_matched_rule=first_result.matched_rule,
        dry_run=True,
    )

    assert second_result.matched_rule is rule
    assert second_result.action_triggered is False
    action.execute.assert_not_called()


@pytest.mark.parametrize(
    ("dry_run", "expected_execution_count"),
    [
        (False, 1),
        (True, 0),
    ],
)
def test_rule_engine_evaluate_executes_actions_only_without_dry_run(
    dry_run: bool,
    expected_execution_count: int,
) -> None:
    condition = make_condition(True)
    action = make_action()
    rule = _make_rule("Test rule", condition, action)

    RuleEngine((rule,)).evaluate(dry_run=dry_run)

    # The conditions are evaluated in both cases, otherwise a dry run would be meaningless
    condition.evaluate.assert_called_once_with()
    assert action.execute.call_count == expected_execution_count
