import pytest

from powerrules.engine.exceptions import ActionExecutionError, ConditionEvaluationError
from powerrules.engine.rule_engine import Rule, RuleEngine
from tests.dummies import Dummy_Action, Dummy_Condition


def test_rule_engine_executes_action_when_condition_matches() -> None:
    condition = Dummy_Condition(given_result=True)
    action = Dummy_Action()

    rule = Rule(
        name="Test rule",
        condition=condition,
        action=action,
    )

    result = RuleEngine((rule,)).evaluate()

    assert result.matched_rule is rule
    assert condition.evaluation_count == 1
    assert action.execution_count == 1


def test_rule_engine_skips_non_matching_rule() -> None:
    condition = Dummy_Condition(given_result=False)
    action = Dummy_Action()

    rule = Rule(
        name="Test rule",
        condition=condition,
        action=action,
    )

    result = RuleEngine((rule,)).evaluate()

    assert result.matched_rule is None
    assert condition.evaluation_count == 1
    assert action.execution_count == 0


def test_rule_engine_evaluates_rules_from_top_to_bottom() -> None:
    first_condition = Dummy_Condition(given_result=False)
    first_action = Dummy_Action()

    second_condition = Dummy_Condition(given_result=True)
    second_action = Dummy_Action()

    rules = (
        Rule(
            name="First test rule",
            condition=first_condition,
            action=first_action,
        ),
        Rule(
            name="Second test rule",
            condition=second_condition,
            action=second_action,
        ),
    )

    result = RuleEngine(rules).evaluate()

    assert result.matched_rule is rules[1]
    assert first_condition.evaluation_count == 1
    assert first_action.execution_count == 0
    assert second_condition.evaluation_count == 1
    assert second_action.execution_count == 1


def test_rule_engine_stops_after_first_matching_rule() -> None:
    first_condition = Dummy_Condition(given_result=True)
    first_action = Dummy_Action()

    second_condition = Dummy_Condition(given_result=True)
    second_action = Dummy_Action()

    rules = (
        Rule(
            name="First test rule",
            condition=first_condition,
            action=first_action,
        ),
        Rule(
            name="Second test rule",
            condition=second_condition,
            action=second_action,
        ),
    )

    result = RuleEngine(rules).evaluate()

    assert result.matched_rule is rules[0]
    assert first_action.execution_count == 1
    # The second rule should not even be evaluated
    assert second_condition.evaluation_count == 0
    assert second_action.execution_count == 0


def test_rule_engine_skips_disabled_rules() -> None:
    condition = Dummy_Condition(given_result=True)
    action = Dummy_Action()

    rule = Rule(
        name="Disabled test rule",
        condition=condition,
        action=action,
        enabled=False,
    )

    result = RuleEngine((rule,)).evaluate()

    assert result.matched_rule is None
    assert condition.evaluation_count == 0
    assert action.execution_count == 0


def test_rule_engine_returns_no_match_when_no_rule_matches() -> None:
    first_condition = Dummy_Condition(given_result=False)
    first_action = Dummy_Action()

    second_condition = Dummy_Condition(given_result=False)
    second_action = Dummy_Action()

    rules = (
        Rule(
            name="First test rule",
            condition=first_condition,
            action=first_action,
        ),
        Rule(
            name="Second test rule",
            condition=second_condition,
            action=second_action,
        ),
    )

    result = RuleEngine(rules).evaluate()

    assert result.matched_rule is None
    assert first_action.execution_count == 0
    assert second_action.execution_count == 0


# This should not happen in practice due to YAML validation
def test_rule_engine_returns_no_match_for_empty_rule_list() -> None:
    result = RuleEngine(()).evaluate()

    assert result.matched_rule is None


######################
# Error handling tests
######################


def test_rule_engine_propagates_condition_evaluation_error() -> None:
    action = Dummy_Action()

    rule = Rule(
        name="Failing test rule",
        condition=Dummy_Condition(
            given_result=True,
            given_exception=ConditionEvaluationError("Test condition failed"),
        ),
        action=action,
    )

    with pytest.raises(ConditionEvaluationError, match="Test condition failed"):
        RuleEngine((rule,)).evaluate()

    assert action.execution_count == 0


def test_rule_engine_stops_after_condition_evaluation_error() -> None:
    first_rule = Rule(
        name="Failing test rule",
        condition=Dummy_Condition(
            given_result=True,
            given_exception=ConditionEvaluationError("Test condition failed"),
        ),
        action=Dummy_Action(),
    )

    second_condition = Dummy_Condition(given_result=True)
    second_action = Dummy_Action()

    second_rule = Rule(
        name="Second test rule",
        condition=second_condition,
        action=second_action,
    )

    with pytest.raises(ConditionEvaluationError):
        RuleEngine((first_rule, second_rule)).evaluate()

    assert second_condition.evaluation_count == 0
    assert second_action.execution_count == 0


def test_rule_engine_propagates_action_execution_error() -> None:
    condition = Dummy_Condition(given_result=True)

    rule = Rule(
        name="Failing test rule",
        condition=condition,
        action=Dummy_Action(given_exception=ActionExecutionError("Test action failed")),
    )

    with pytest.raises(ActionExecutionError, match="Test action failed"):
        RuleEngine((rule,)).evaluate()


def test_rule_engine_stops_after_action_execution_error() -> None:
    first_rule = Rule(
        name="Failing test rule",
        condition=Dummy_Condition(given_result=True),
        action=Dummy_Action(given_exception=ActionExecutionError("Test action failed")),
    )

    second_condition = Dummy_Condition(given_result=True)
    second_action = Dummy_Action()

    second_rule = Rule(
        name="Second test rule",
        condition=second_condition,
        action=second_action,
    )

    with pytest.raises(ActionExecutionError):
        RuleEngine((first_rule, second_rule)).evaluate()

    assert second_condition.evaluation_count == 0
    assert second_action.execution_count == 0


def test_rule_engine_find_match_returns_matching_rule() -> None:
    condition = Dummy_Condition(given_result=True)
    action = Dummy_Action()

    rule = Rule(
        name="Test rule",
        condition=condition,
        action=action,
    )

    matched_rule = RuleEngine((rule,)).find_match()

    assert matched_rule is rule
    assert condition.evaluation_count == 1
    assert action.execution_count == 0


def test_rule_engine_find_match_returns_none_when_no_rule_matches() -> None:
    rule = Rule(
        name="Test rule",
        condition=Dummy_Condition(given_result=False),
        action=Dummy_Action(),
    )

    matched_rule = RuleEngine((rule,)).find_match()

    assert matched_rule is None


def test_rule_engine_find_match_returns_first_matching_rule() -> None:
    first_rule = Rule(
        name="First rule",
        condition=Dummy_Condition(given_result=True),
        action=Dummy_Action(),
    )

    second_rule = Rule(
        name="Second rule",
        condition=Dummy_Condition(given_result=True),
        action=Dummy_Action(),
    )

    matched_rule = RuleEngine((first_rule, second_rule)).find_match()

    assert matched_rule is first_rule
    assert second_rule.condition.evaluation_count == 0  # type: ignore (a "real" condition does not have this attribute, but the dummy condition does)


##############################################
# previous_matched_rule / action_triggered tests
##############################################


def test_rule_engine_evaluate_triggers_action_on_first_match() -> None:
    condition = Dummy_Condition(given_result=True)
    action = Dummy_Action()

    rule = Rule(
        name="Test rule",
        condition=condition,
        action=action,
    )

    result = RuleEngine((rule,)).evaluate()

    assert result.matched_rule is rule
    assert result.action_triggered is True
    assert action.execution_count == 1


def test_rule_engine_evaluate_does_not_retrigger_same_matched_rule() -> None:
    condition = Dummy_Condition(given_result=True)
    action = Dummy_Action()

    rule = Rule(
        name="Test rule",
        condition=condition,
        action=action,
    )

    engine = RuleEngine((rule,))

    first_result = engine.evaluate()
    second_result = engine.evaluate(previous_matched_rule=first_result.matched_rule)

    assert second_result.matched_rule is rule
    assert second_result.action_triggered is False
    # The action was only executed once, not on the second (repeated) match
    assert action.execution_count == 1


def test_rule_engine_evaluate_retriggers_after_no_match_in_between() -> None:
    condition = Dummy_Condition(given_result=True)
    action = Dummy_Action()

    rule = Rule(
        name="Test rule",
        condition=condition,
        action=action,
    )

    engine = RuleEngine((rule,))

    first_result = engine.evaluate()
    # The rule no longer matches (e.g. condition changed), so there is no previous match
    third_result = engine.evaluate(previous_matched_rule=None)

    assert first_result.action_triggered is True
    assert third_result.matched_rule is rule
    assert third_result.action_triggered is True
    # Triggered once on the first call and once again after the "no match" gap
    assert action.execution_count == 2


def test_rule_engine_evaluate_retriggers_when_matched_rule_changes() -> None:
    first_action = Dummy_Action()
    second_action = Dummy_Action()

    first_rule = Rule(
        name="First rule",
        condition=Dummy_Condition(given_result=True),
        action=first_action,
    )
    second_rule = Rule(
        name="Second rule",
        condition=Dummy_Condition(given_result=False),
        action=second_action,
    )

    engine = RuleEngine((first_rule, second_rule))

    first_result = engine.evaluate()

    # Now the second rule matches instead of the first one
    first_rule.condition.given_result = False  # type: ignore (Dummy_Condition has this attribute)
    second_rule.condition.given_result = True  # type: ignore (Dummy_Condition has this attribute)

    second_result = engine.evaluate(previous_matched_rule=first_result.matched_rule)

    assert first_result.matched_rule is first_rule
    assert second_result.matched_rule is second_rule
    assert second_result.action_triggered is True
    assert second_action.execution_count == 1


def test_rule_engine_evaluate_does_not_trigger_action_for_no_match() -> None:
    condition = Dummy_Condition(given_result=False)
    action = Dummy_Action()

    rule = Rule(
        name="Test rule",
        condition=condition,
        action=action,
    )

    result = RuleEngine((rule,)).evaluate()

    assert result.matched_rule is None
    assert result.action_triggered is False
    assert action.execution_count == 0


######################
# dry_run tests
######################


def test_rule_engine_evaluate_dry_run_reports_trigger_without_executing() -> None:
    condition = Dummy_Condition(given_result=True)
    action = Dummy_Action()

    rule = Rule(
        name="Test rule",
        condition=condition,
        action=action,
    )

    result = RuleEngine((rule,)).evaluate(dry_run=True)

    assert result.matched_rule is rule
    assert result.action_triggered is True
    assert action.execution_count == 0


def test_rule_engine_evaluate_dry_run_does_not_retrigger_same_matched_rule() -> None:
    condition = Dummy_Condition(given_result=True)
    action = Dummy_Action()

    rule = Rule(
        name="Test rule",
        condition=condition,
        action=action,
    )

    engine = RuleEngine((rule,))

    first_result = engine.evaluate(dry_run=True)
    second_result = engine.evaluate(
        previous_matched_rule=first_result.matched_rule,
        dry_run=True,
    )

    assert second_result.matched_rule is rule
    assert second_result.action_triggered is False
    assert action.execution_count == 0
