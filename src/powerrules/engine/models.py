from dataclasses import dataclass

from powerrules.actions.base import Action
from powerrules.conditions.base import Condition


@dataclass(frozen=True)
class Rule:
    """A rule consisting of a condition and an action."""

    name: str
    condition: Condition
    action: Action
    enabled: bool = True


@dataclass(frozen=True)
class RuleSet:
    """Represent an ordered set of PowerRules rules."""

    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class RuleEvaluationResult:
    """Represent the result of evaluating the rule set."""

    matched_rule: Rule | None
    # True when a rule matched and it was not the previous_matched_rule
    action_triggered: bool = False
