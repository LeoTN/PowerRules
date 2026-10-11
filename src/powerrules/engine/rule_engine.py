from collections.abc import Sequence

from powerrules.engine.models import Rule, RuleEvaluationResult


class RuleEngine:
    def __init__(self, rules: Sequence[Rule]):
        self.rules = tuple(rules)

    def find_match(self) -> Rule | None:
        """Find the first enabled rule whose condition matches.

        Returns:
            The first matching rule, or None if no rule matches.

        Raises:
            ConditionEvaluationError: If a condition cannot be evaluated.
        """
        for rule in self.rules:
            if not rule.enabled:
                continue

            if rule.condition.evaluate():
                return rule

        return None

    def evaluate(
        self,
        previous_matched_rule: Rule | None = None,
        dry_run: bool = False,
    ) -> RuleEvaluationResult:
        """Evaluate rules and execute the actions of a newly matching rule.

        A match is considered "new" if a rule matches and it is not the same rule as "previous_matched_rule".
        This lets repeated calls (e.g. from a polling loop) trigger the actions only once per state change,
        instead of on every call while the same rule keeps matching.

        Args:
            previous_matched_rule: The rule that matched on the previous evaluation, if any.
                Defaults to None, so any match is considered new.
            dry_run: If True, determine whether the actions would trigger without actually executing them.

        Returns:
            The result of the rule evaluation, including whether the actions were
            (or, in a dry run, would have been) triggered.

        Raises:
            ConditionEvaluationError: If a condition cannot be evaluated.
            ActionExecutionError: If an action of a matching rule cannot be executed.
                The remaining actions of the rule are skipped.
        """
        matched_rule = self.find_match()
        action_triggered = False

        if matched_rule is not None and matched_rule is not previous_matched_rule:
            action_triggered = True

            if not dry_run:
                # Execute the actions in order, e.g. run a script and shut down afterwards
                for action in matched_rule.actions:
                    action.execute()

        return RuleEvaluationResult(
            matched_rule=matched_rule,
            action_triggered=action_triggered,
        )
