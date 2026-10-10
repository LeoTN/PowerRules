import pytest

from powerrules.engine.models import Rule, RuleEvaluationResult, RuleSet
from tests.mocks import make_action, make_condition

############
# Rule tests
############


def test_rule_uses_expected_defaults() -> None:
    condition = make_condition()
    action = make_action()

    rule = Rule(
        name="Test rule",
        condition=condition,
        actions=(action,),
    )

    assert rule.name == "Test rule"
    assert rule.condition is condition
    assert rule.actions == (action,)
    assert rule.enabled is True


def test_rule_can_be_disabled() -> None:
    rule = Rule(
        name="Disabled test rule",
        condition=make_condition(),
        actions=(make_action(),),
        enabled=False,
    )

    assert rule.enabled is False


def test_rule_can_contain_multiple_actions_in_order() -> None:
    first_action = make_action("First action")
    second_action = make_action("Second action")

    rule = Rule(
        name="Test rule",
        condition=make_condition(),
        actions=(first_action, second_action),
    )

    assert rule.actions == (first_action, second_action)


def test_rule_is_immutable() -> None:
    rule = Rule(
        name="Test rule",
        condition=make_condition(),
        actions=(make_action(),),
    )

    with pytest.raises(AttributeError):
        rule.name = "Modified rule"  # type: ignore (ignore this Pylance error even though it is correct)


def test_rule_actions_are_immutable() -> None:
    rule = Rule(
        name="Test rule",
        condition=make_condition(),
        actions=(make_action(),),
    )

    with pytest.raises(AttributeError):
        rule.actions = ()  # type: ignore (ignore this Pylance error even though it is correct)


###############
# RuleSet tests
###############


def test_rule_set_contains_rules() -> None:
    rule = Rule(
        name="Test rule",
        condition=make_condition(),
        actions=(make_action(),),
    )

    rule_set = RuleSet(rules=(rule,))

    assert rule_set.rules == (rule,)


def test_rule_set_can_contain_multiple_rules() -> None:
    first_rule = Rule(
        name="First test rule",
        condition=make_condition(),
        actions=(make_action(),),
    )

    second_rule = Rule(
        name="Second test rule",
        condition=make_condition(),
        actions=(make_action(),),
    )

    rule_set = RuleSet(rules=(first_rule, second_rule))

    assert rule_set.rules == (
        first_rule,
        second_rule,
    )


def test_rule_set_can_be_empty() -> None:
    assert RuleSet(rules=()).rules == ()


def test_rule_set_is_immutable() -> None:
    rule_set = RuleSet(rules=())

    with pytest.raises(AttributeError):
        rule_set.rules = ()  # type: ignore (ignore this Pylance error even though it is correct)


############################
# RuleEvaluationResult tests
############################


def test_rule_evaluation_result_uses_expected_defaults() -> None:
    result = RuleEvaluationResult(matched_rule=None)

    assert result.matched_rule is None
    assert result.action_triggered is False


def test_rule_evaluation_result_contains_matched_rule() -> None:
    rule = Rule(
        name="Test rule",
        condition=make_condition(),
        actions=(make_action(),),
    )

    result = RuleEvaluationResult(matched_rule=rule, action_triggered=True)

    assert result.matched_rule is rule
    assert result.action_triggered is True


def test_rule_evaluation_result_is_immutable() -> None:
    result = RuleEvaluationResult(matched_rule=None)

    with pytest.raises(AttributeError):
        result.action_triggered = True  # type: ignore (ignore this Pylance error even though it is correct)
