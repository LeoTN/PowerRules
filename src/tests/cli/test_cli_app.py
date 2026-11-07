import re
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from powerrules.application.runtime import DEFAULT_EVALUATION_INTERVAL_SECONDS
from powerrules.cli.app import app
from powerrules.cli.errors import EXIT_POLICY_ERROR, EXIT_RUNTIME_ERROR
from powerrules.engine.exceptions import ActionExecutionError, ConditionEvaluationError
from powerrules.engine.models import RuleEvaluationResult
from tests.factories import make_policy_yaml, make_rule_with_actions
from tests.helpers import get_plain_output, write_policy

runner = CliRunner()

VALID_POLICY = make_policy_yaml()


@pytest.fixture
def runtime() -> Iterator[Mock]:
    """Replace the runtime which is created by the commands and return its instance."""
    with patch("powerrules.cli.app.PowerRulesRuntime") as runtime_class:
        yield runtime_class.return_value


#############
# Basic tests
#############


def test_cli_displays_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "A rule-based command automation tool" in get_plain_output(result)


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
    assert "Manage PowerRules policies." in get_plain_output(result)


################
# validate tests
################


def test_cli_policy_validate(tmp_path: Path) -> None:
    policy_file = write_policy(tmp_path, VALID_POLICY)

    result = runner.invoke(app, ["policy", "validate", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert f"Policy '{policy_file}' is valid" in get_plain_output(result)


def test_cli_policy_validate_rejects_invalid_policy(tmp_path: Path) -> None:
    policy_file = write_policy(
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
    assert "Policy validation failed" in get_plain_output(result, "output")
    assert "rules.0.conditions.process.exists" in get_plain_output(result, "output")


def test_cli_policy_validate_rejects_former_action_format(tmp_path: Path) -> None:
    policy_file = write_policy(
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
    assert "Policy validation failed" in get_plain_output(result, "output")


def test_cli_policy_validate_rejects_rule_without_actions(tmp_path: Path) -> None:
    policy_file = write_policy(
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
    assert "at least 1 item" in get_plain_output(result, "output")


def test_cli_policy_validate_rejects_invalid_yaml(tmp_path: Path) -> None:
    policy_file = write_policy(tmp_path, 'rules:\n  - name: "Broken rule\n')

    result = runner.invoke(app, ["policy", "validate", "--policy", str(policy_file)])

    assert result.exit_code == EXIT_POLICY_ERROR
    assert "Failed to parse policy file" in get_plain_output(result, "output")


def test_cli_policy_validate_reports_missing_policy(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["policy", "validate", "--policy", str(tmp_path / "missing.yaml")]
    )

    assert result.exit_code == EXIT_POLICY_ERROR
    assert "Policy file not found" in get_plain_output(result, "output")


############
# show tests
############


def test_cli_policy_show(tmp_path: Path) -> None:
    policy_file = write_policy(
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
    assert "1. First test rule [enabled]" in get_plain_output(result)
    assert "2. Disabled test rule [disabled]" in get_plain_output(result)


##################
# run --once tests
##################


def test_cli_policy_run_once_reports_matching_rule(runtime: Mock) -> None:
    runtime.run_once.return_value = RuleEvaluationResult(
        matched_rule=make_rule_with_actions("Cleanup", "Shutdown")
    )

    result = runner.invoke(app, ["policy", "run", "--once"])

    assert result.exit_code == 0
    assert (
        "Rule 'Test rule' matched, executed actions: 'Cleanup', 'Shutdown'"
        in get_plain_output(result)
    )
    runtime.run_once.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"), dry_run=False
    )
    runtime.run_continuously.assert_not_called()


def test_cli_policy_run_once_reports_no_match(runtime: Mock) -> None:
    runtime.run_once.return_value = RuleEvaluationResult(matched_rule=None)

    result = runner.invoke(app, ["policy", "run", "--once"])

    assert result.exit_code == 0
    assert "No rule matched" in get_plain_output(result)
    runtime.run_once.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"), dry_run=False
    )
    runtime.run_continuously.assert_not_called()


def test_cli_policy_run_once_reports_dry_run_match(runtime: Mock) -> None:
    runtime.run_once.return_value = RuleEvaluationResult(
        matched_rule=make_rule_with_actions("Cleanup", "Shutdown")
    )

    result = runner.invoke(app, ["policy", "run", "--once", "--dry-run"])

    assert result.exit_code == 0
    assert (
        "[DRY RUN] Rule 'Test rule' matched, would have executed actions: 'Cleanup', 'Shutdown'"
        in get_plain_output(result)
    )
    assert "executed actions:" not in get_plain_output(result).replace(
        "would have executed", ""
    )
    runtime.run_once.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"), dry_run=True
    )


def test_cli_policy_run_once_uses_custom_policy_path(
    runtime: Mock, tmp_path: Path
) -> None:
    policy_file = write_policy(tmp_path, VALID_POLICY)
    runtime.run_once.return_value = RuleEvaluationResult(matched_rule=None)

    result = runner.invoke(
        app, ["policy", "run", "--once", "--policy", str(policy_file)]
    )

    assert result.exit_code == 0
    assert "No rule matched" in get_plain_output(result)
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
    assert message in get_plain_output(result, "output")


########################
# run (continuous) tests
########################


def test_cli_policy_run_calls_run_continuously(runtime: Mock) -> None:
    runtime.run_continuously.return_value = iter([])

    result = runner.invoke(app, ["policy", "run"])

    assert result.exit_code == 0
    runtime.run_continuously.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"),
        evaluation_interval=DEFAULT_EVALUATION_INTERVAL_SECONDS,
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
        evaluation_interval=DEFAULT_EVALUATION_INTERVAL_SECONDS,
        stop_on_match=False,
        dry_run=False,
    )


def test_cli_policy_run_passes_stop_on_match(runtime: Mock) -> None:
    runtime.run_continuously.return_value = iter([])

    result = runner.invoke(app, ["policy", "run", "--stop-on-match"])

    assert result.exit_code == 0
    runtime.run_continuously.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"),
        evaluation_interval=DEFAULT_EVALUATION_INTERVAL_SECONDS,
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
        evaluation_interval=DEFAULT_EVALUATION_INTERVAL_SECONDS,
        stop_on_match=True,
        dry_run=False,
    )


def test_cli_policy_run_logs_triggered_match(runtime: Mock) -> None:
    runtime.run_continuously.return_value = iter(
        [
            RuleEvaluationResult(
                matched_rule=make_rule_with_actions("Cleanup", "Shutdown"),
                action_triggered=True,
            )
        ]
    )

    result = runner.invoke(app, ["policy", "run", "--stop-on-match"])

    assert result.exit_code == 0
    assert (
        "Rule 'Test rule' matched, executed actions: 'Cleanup', 'Shutdown'"
        in get_plain_output(result)
    )


def test_cli_policy_run_logs_dry_run_match(runtime: Mock) -> None:
    runtime.run_continuously.return_value = iter(
        [
            RuleEvaluationResult(
                matched_rule=make_rule_with_actions("Shutdown"), action_triggered=True
            )
        ]
    )

    result = runner.invoke(app, ["policy", "run", "--dry-run", "--stop-on-match"])

    assert result.exit_code == 0
    assert (
        "[DRY RUN] Rule 'Test rule' matched, would have executed actions: 'Shutdown'"
        in get_plain_output(result)
    )
    runtime.run_continuously.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"),
        evaluation_interval=DEFAULT_EVALUATION_INTERVAL_SECONDS,
        stop_on_match=True,
        dry_run=True,
    )


def test_cli_policy_run_logs_stopping_evaluation_on_stop_on_match(
    runtime: Mock,
) -> None:
    runtime.run_continuously.return_value = iter(
        [
            RuleEvaluationResult(
                matched_rule=make_rule_with_actions(), action_triggered=True
            )
        ]
    )

    result = runner.invoke(app, ["policy", "run", "--stop-on-match"])

    assert result.exit_code == 0
    assert "Rule matched, stopping evaluation" in get_plain_output(result)


def test_cli_policy_run_does_not_log_stopping_without_stop_on_match(
    runtime: Mock,
) -> None:
    runtime.run_continuously.return_value = iter(
        [
            RuleEvaluationResult(
                matched_rule=make_rule_with_actions(), action_triggered=True
            )
        ]
    )

    result = runner.invoke(app, ["policy", "run"])

    assert result.exit_code == 0
    assert "stopping evaluation" not in get_plain_output(result)


def test_cli_policy_run_does_not_log_when_no_match(runtime: Mock) -> None:
    runtime.run_continuously.return_value = iter(
        [RuleEvaluationResult(matched_rule=None, action_triggered=False)]
    )

    result = runner.invoke(app, ["policy", "run", "--stop-on-match"])

    assert result.exit_code == 0
    assert "matched" not in get_plain_output(result)


def test_cli_policy_run_does_not_log_repeated_match(runtime: Mock) -> None:
    rule = make_rule_with_actions()
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
    assert message in get_plain_output(result, "output")


@pytest.mark.parametrize("interval", ["0.5", "2", "3600"])
def test_cli_policy_run_passes_interval(runtime: Mock, interval: str) -> None:
    runtime.run_continuously.return_value = iter([])

    result = runner.invoke(app, ["policy", "run", "--interval", interval])

    assert result.exit_code == 0
    assert runtime.run_continuously.call_args.kwargs["evaluation_interval"] == float(
        interval
    )


# The exit code 2 is the one of an invalid usage. The text of the error is wrapped by the formatting of the error panel,
# so only the name of the option is checked
@pytest.mark.parametrize("interval", ["0", "-1", "nan", "inf", "1e300", "abc"])
def test_cli_policy_run_rejects_invalid_interval(runtime: Mock, interval: str) -> None:
    result = runner.invoke(app, ["policy", "run", f"--interval={interval}"])

    assert result.exit_code == EXIT_POLICY_ERROR
    assert "--interval" in get_plain_output(result, "output")
    runtime.run_continuously.assert_not_called()


# The interval has no effect with "--once", but an invalid one is still a mistake
def test_cli_policy_run_validates_interval_together_with_once(runtime: Mock) -> None:
    result = runner.invoke(app, ["policy", "run", "--once", "--interval", "0"])

    assert result.exit_code == EXIT_POLICY_ERROR
    runtime.run_once.assert_not_called()
