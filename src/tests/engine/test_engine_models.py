import pytest

from powerrules.engine.models import Rule, RuleEvaluationResult, RuleSet
from tests.factories import make_action, make_condition, make_rule

############
# Rule tests
############


def test_rule_uses_expected_defaults() -> None:
    condition = make_condition()
    action = make_action()

    # The model is created directly, because "make_rule()" always passes "enabled" explicitly
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
    rule = make_rule("Disabled test rule", enabled=False)

    assert rule.enabled is False


def test_rule_can_contain_multiple_actions_in_order() -> None:
    first_action = make_action("First action")
    second_action = make_action("Second action")

    rule = make_rule(actions=[first_action, second_action])

    assert rule.actions == (first_action, second_action)


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("name", "Modified rule"),
        ("actions", ()),
    ],
)
def test_rule_is_immutable(
    attribute: str,
    value: object,
) -> None:
    rule = make_rule()

    with pytest.raises(AttributeError):
        setattr(rule, attribute, value)


###############
# RuleSet tests
###############


@pytest.mark.parametrize("rule_count", [0, 1, 2])
def test_rule_set_contains_rules_in_order(rule_count: int) -> None:
    rules = tuple(make_rule(f"Test rule {number}") for number in range(rule_count))

    assert RuleSet(rules=rules).rules == rules


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
    rule = make_rule()

    result = RuleEvaluationResult(matched_rule=rule, action_triggered=True)

    assert result.matched_rule is rule
    assert result.action_triggered is True


def test_rule_evaluation_result_is_immutable() -> None:
    result = RuleEvaluationResult(matched_rule=None)

    with pytest.raises(AttributeError):
        result.action_triggered = True  # type: ignore (ignore this Pylance error even though it is correct)
