import re
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from powerrules.cli.app import app
from powerrules.cli.errors import EXIT_POLICY_ERROR, EXIT_RUNTIME_ERROR
from powerrules.engine.exceptions import ActionExecutionError, ConditionEvaluationError
from powerrules.engine.models import Rule, RuleEvaluationResult
from tests.mocks import make_action, make_condition

runner = CliRunner()

VALID_POLICY = """
rules:
  - name: "Test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - run: "echo test"
"""


@pytest.fixture
def runtime() -> Iterator[Mock]:
    """Replace the runtime which is created by the commands and return its instance."""
    with patch("powerrules.cli.app.PowerRulesRuntime") as runtime_class:
        yield runtime_class.return_value


def _write_policy(tmp_path: Path, content: str = VALID_POLICY) -> Path:
    """Write a policy file into the temporary directory."""
    policy_file = tmp_path / "powerrules.yaml"
    policy_file.write_text(content, encoding="utf-8")

    return policy_file


def _make_rule(*action_names: str) -> Rule:
    """Create a matching rule with actions of the given names."""
    return Rule(
        name="Test rule",
        condition=make_condition(True),
        actions=tuple(make_action(name) for name in action_names or ("Shutdown",)),
    )


#############
# Basic tests
#############


def test_cli_displays_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "A rule-based command automation tool" in result.stdout


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    # The version is derived from the Git tags, so it can also be a development version (e.g. 0.2.0.post3.dev0+28c1684)
    assert re.fullmatch(
        r"PowerRules \d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?(?:\.post\d+)?(?:\.dev\d+)?(?:\+[0-9a-zA-Z.]+)?",
        result.stdout.strip(),
    )


def test_cli_policy_displays_help() -> None:
    result = runner.invoke(app, ["policy", "--help"])

    assert result.exit_code == 0
    assert "Manage PowerRules policies." in result.stdout


################
# validate tests
################


def test_cli_policy_validate(tmp_path: Path) -> None:
    policy_file = _write_policy(tmp_path)

    result = runner.invoke(app, ["policy", "validate", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert f"Policy '{policy_file}' is valid" in result.stdout


def test_cli_policy_validate_rejects_invalid_policy(tmp_path: Path) -> None:
    policy_file = _write_policy(
        tmp_path,
        """
rules:
  - name: "Invalid test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: "false"
    actions:
      - run: "echo test"
""",
    )

    result = runner.invoke(app, ["policy", "validate", "--policy", str(policy_file)])

    assert result.exit_code == EXIT_POLICY_ERROR
    assert "Policy validation failed" in result.output
    assert "rules.0.conditions.process.exists" in result.output


def test_cli_policy_validate_rejects_former_action_format(tmp_path: Path) -> None:
    policy_file = _write_policy(
        tmp_path,
        """
rules:
  - name: "Former format test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    action:
      type: shutdown
""",
    )

    result = runner.invoke(app, ["policy", "validate", "--policy", str(policy_file)])

    assert result.exit_code == EXIT_POLICY_ERROR
    assert "Policy validation failed" in result.output


def test_cli_policy_validate_rejects_rule_without_actions(tmp_path: Path) -> None:
    policy_file = _write_policy(
        tmp_path,
        """
rules:
  - name: "Test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions: []
""",
    )

    result = runner.invoke(app, ["policy", "validate", "--policy", str(policy_file)])

    assert result.exit_code == EXIT_POLICY_ERROR
    assert "at least 1 item" in result.output


def test_cli_policy_validate_rejects_invalid_yaml(tmp_path: Path) -> None:
    policy_file = _write_policy(tmp_path, 'rules:\n  - name: "Broken rule\n')

    result = runner.invoke(app, ["policy", "validate", "--policy", str(policy_file)])

    assert result.exit_code == EXIT_POLICY_ERROR
    assert "Failed to parse policy file" in result.output


def test_cli_policy_validate_reports_missing_policy(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["policy", "validate", "--policy", str(tmp_path / "missing.yaml")]
    )

    assert result.exit_code == EXIT_POLICY_ERROR
    assert "Policy file not found" in result.output


############
# show tests
############


def test_cli_policy_show(tmp_path: Path) -> None:
    policy_file = _write_policy(
        tmp_path,
        """
rules:
  - name: "First test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - run: "echo first"

  - name: "Disabled test rule"
    enabled: false
    conditions:
      process:
        name: "maintenance.exe"
        exists: false
    actions:
      - run: "echo second"
""",
    )

    result = runner.invoke(app, ["policy", "show", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert "1. First test rule [enabled]" in result.stdout
    assert "2. Disabled test rule [disabled]" in result.stdout


##################
# run --once tests
##################


def test_cli_policy_run_once_reports_matching_rule(runtime: Mock) -> None:
    runtime.run_once.return_value = RuleEvaluationResult(
        matched_rule=_make_rule("Cleanup", "Shutdown")
    )

    result = runner.invoke(app, ["policy", "run", "--once"])

    assert result.exit_code == 0
    assert (
        "Rule 'Test rule' matched, executed actions: 'Cleanup', 'Shutdown'"
        in result.stdout
    )
    runtime.run_once.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"), dry_run=False
    )
    runtime.run_continuously.assert_not_called()


def test_cli_policy_run_once_reports_no_match(runtime: Mock) -> None:
    runtime.run_once.return_value = RuleEvaluationResult(matched_rule=None)

    result = runner.invoke(app, ["policy", "run", "--once"])

    assert result.exit_code == 0
    assert "No rule matched" in result.stdout
    runtime.run_once.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"), dry_run=False
    )
    runtime.run_continuously.assert_not_called()


def test_cli_policy_run_once_reports_dry_run_match(runtime: Mock) -> None:
    runtime.run_once.return_value = RuleEvaluationResult(
        matched_rule=_make_rule("Cleanup", "Shutdown")
    )

    result = runner.invoke(app, ["policy", "run", "--once", "--dry-run"])

    assert result.exit_code == 0
    assert (
        "[DRY RUN] Rule 'Test rule' matched, would have executed actions: 'Cleanup', 'Shutdown'"
        in result.stdout
    )
    assert "executed actions:" not in result.stdout.replace("would have executed", "")
    runtime.run_once.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"), dry_run=True
    )


def test_cli_policy_run_once_uses_custom_policy_path(
    runtime: Mock, tmp_path: Path
) -> None:
    policy_file = _write_policy(tmp_path)
    runtime.run_once.return_value = RuleEvaluationResult(matched_rule=None)

    result = runner.invoke(
        app, ["policy", "run", "--once", "--policy", str(policy_file)]
    )

    assert result.exit_code == 0
    assert "No rule matched" in result.stdout
    runtime.run_once.assert_called_once_with(
        configuration_path=policy_file, dry_run=False
    )


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            ConditionEvaluationError("Test condition failed"),
            "Failed to evaluate condition: Test condition failed",
        ),
        (
            ActionExecutionError("Test action failed"),
            "Failed to execute action: Test action failed",
        ),
    ],
)
def test_cli_policy_run_once_reports_runtime_errors(
    runtime: Mock,
    error: Exception,
    message: str,
) -> None:
    runtime.run_once.side_effect = error

    result = runner.invoke(app, ["policy", "run", "--once"])

    assert result.exit_code == EXIT_RUNTIME_ERROR
    assert message in result.output


########################
# run (continuous) tests
########################


def test_cli_policy_run_calls_run_continuously(runtime: Mock) -> None:
    runtime.run_continuously.return_value = iter([])

    result = runner.invoke(app, ["policy", "run"])

    assert result.exit_code == 0
    runtime.run_continuously.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"),
        stop_on_match=False,
        dry_run=False,
    )
    runtime.run_once.assert_not_called()


def test_cli_policy_run_uses_custom_policy_path(runtime: Mock, tmp_path: Path) -> None:
    policy_file = tmp_path / "custom-policy.yaml"
    runtime.run_continuously.return_value = iter([])

    result = runner.invoke(app, ["policy", "run", "--policy", str(policy_file)])

    assert result.exit_code == 0
    runtime.run_continuously.assert_called_once_with(
        configuration_path=policy_file,
        stop_on_match=False,
        dry_run=False,
    )


def test_cli_policy_run_passes_stop_on_match(runtime: Mock) -> None:
    runtime.run_continuously.return_value = iter([])

    result = runner.invoke(app, ["policy", "run", "--stop-on-match"])

    assert result.exit_code == 0
    runtime.run_continuously.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"),
        stop_on_match=True,
        dry_run=False,
    )


def test_cli_policy_run_passes_custom_policy_and_stop_on_match(
    runtime: Mock, tmp_path: Path
) -> None:
    policy_file = tmp_path / "custom-policy.yaml"
    runtime.run_continuously.return_value = iter([])

    result = runner.invoke(
        app, ["policy", "run", "--policy", str(policy_file), "--stop-on-match"]
    )

    assert result.exit_code == 0
    runtime.run_continuously.assert_called_once_with(
        configuration_path=policy_file,
        stop_on_match=True,
        dry_run=False,
    )


def test_cli_policy_run_logs_triggered_match(runtime: Mock) -> None:
    runtime.run_continuously.return_value = iter(
        [
            RuleEvaluationResult(
                matched_rule=_make_rule("Cleanup", "Shutdown"), action_triggered=True
            )
        ]
    )

    result = runner.invoke(app, ["policy", "run", "--stop-on-match"])

    assert result.exit_code == 0
    assert (
        "Rule 'Test rule' matched, executed actions: 'Cleanup', 'Shutdown'"
        in result.stdout
    )


def test_cli_policy_run_logs_dry_run_match(runtime: Mock) -> None:
    runtime.run_continuously.return_value = iter(
        [
            RuleEvaluationResult(
                matched_rule=_make_rule("Shutdown"), action_triggered=True
            )
        ]
    )

    result = runner.invoke(app, ["policy", "run", "--dry-run", "--stop-on-match"])

    assert result.exit_code == 0
    assert (
        "[DRY RUN] Rule 'Test rule' matched, would have executed actions: 'Shutdown'"
        in result.stdout
    )
    runtime.run_continuously.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"),
        stop_on_match=True,
        dry_run=True,
    )


def test_cli_policy_run_logs_stopping_evaluation_on_stop_on_match(
    runtime: Mock,
) -> None:
    runtime.run_continuously.return_value = iter(
        [RuleEvaluationResult(matched_rule=_make_rule(), action_triggered=True)]
    )

    result = runner.invoke(app, ["policy", "run", "--stop-on-match"])

    assert result.exit_code == 0
    assert "Rule matched, stopping evaluation" in result.stdout


def test_cli_policy_run_does_not_log_stopping_without_stop_on_match(
    runtime: Mock,
) -> None:
    runtime.run_continuously.return_value = iter(
        [RuleEvaluationResult(matched_rule=_make_rule(), action_triggered=True)]
    )

    result = runner.invoke(app, ["policy", "run"])

    assert result.exit_code == 0
    assert "stopping evaluation" not in result.stdout


def test_cli_policy_run_does_not_log_when_no_match(runtime: Mock) -> None:
    runtime.run_continuously.return_value = iter(
        [RuleEvaluationResult(matched_rule=None, action_triggered=False)]
    )

    result = runner.invoke(app, ["policy", "run", "--stop-on-match"])

    assert result.exit_code == 0
    assert "matched" not in result.stdout


def test_cli_policy_run_does_not_log_repeated_match(runtime: Mock) -> None:
    rule = _make_rule()
    runtime.run_continuously.return_value = iter(
        [
            RuleEvaluationResult(matched_rule=rule, action_triggered=True),
            # Second evaluation: same rule still matches, but the actions were
            # already triggered before, so they should not be logged again
            RuleEvaluationResult(matched_rule=rule, action_triggered=False),
        ]
    )

    result = runner.invoke(app, ["policy", "run"])

    assert result.exit_code == 0
    assert result.stdout.count("matched, executed actions") == 1


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            ConditionEvaluationError("Test condition failed"),
            "Failed to evaluate condition: Test condition failed",
        ),
        (
            ActionExecutionError("Test action failed"),
            "Failed to execute action: Test action failed",
        ),
    ],
)
def test_cli_policy_run_reports_runtime_errors(
    runtime: Mock,
    error: Exception,
    message: str,
) -> None:
    runtime.run_continuously.side_effect = error

    result = runner.invoke(app, ["policy", "run"])

    assert result.exit_code == EXIT_RUNTIME_ERROR
    assert message in result.output
