import re
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from powerrules.actions.power import ShutdownAction
from powerrules.cli.app import app
from powerrules.engine.models import Rule, RuleEvaluationResult
from tests.dummies import Dummy_Action, Dummy_Condition, Dummy_PowerProvider

runner = CliRunner()


def test_cli_displays_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "A rule-based computer power state management tool" in result.stdout


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


def test_cli_policy_validate(tmp_path: Path) -> None:
    policy_file = tmp_path / "powerrules.yaml"
    policy_file.write_text(
        """
rules:
  - name: "Test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    action:
      type: shutdown
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["policy", "validate", "--policy", str(policy_file)],
    )

    assert result.exit_code == 0
    assert f"Policy '{policy_file}' is valid" in result.stdout


def test_cli_policy_validate_rejects_invalid_policy(tmp_path: Path) -> None:
    policy_file = tmp_path / "powerrules.yaml"
    policy_file.write_text(
        """
rules:
  - name: "Invalid test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: "false"
    action:
      type: shutdown
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["policy", "validate", "--policy", str(policy_file)],
    )

    assert result.exit_code != 0


def test_cli_policy_show(tmp_path: Path) -> None:
    policy_file = tmp_path / "powerrules.yaml"
    policy_file.write_text(
        """
rules:
  - name: "First test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    action:
      type: shutdown

  - name: "Disabled test rule"
    enabled: false
    conditions:
      process:
        name: "maintenance.exe"
        exists: false
    action:
      type: sleep
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["policy", "show", "--policy", str(policy_file)],
    )

    assert result.exit_code == 0
    assert "1. First test rule [enabled]" in result.stdout
    assert "2. Disabled test rule [disabled]" in result.stdout


def test_cli_policy_run_once_reports_matching_rule() -> None:
    rule = Rule(
        name="Test rule",
        condition=Dummy_Condition(given_result=True),
        action=Dummy_Action(),
    )
    evaluation_result = RuleEvaluationResult(matched_rule=rule)

    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        mock_runtime.return_value.run_once.return_value = evaluation_result

        result = runner.invoke(
            app,
            ["policy", "run", "--once"],
        )

    assert result.exit_code == 0
    assert "Rule 'Test rule' matched" in result.stdout
    mock_runtime.return_value.run_once.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"), dry_run=False
    )


def test_cli_policy_run_once_reports_no_match() -> None:
    evaluation_result = RuleEvaluationResult(matched_rule=None)

    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        mock_runtime.return_value.run_once.return_value = evaluation_result

        result = runner.invoke(
            app,
            ["policy", "run", "--once"],
        )

    assert result.exit_code == 0
    assert "No rule matched" in result.stdout
    mock_runtime.return_value.run_once.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"), dry_run=False
    )


def test_cli_policy_run_once_uses_custom_policy_path(tmp_path: Path) -> None:
    policy_file = tmp_path / "custom-policy.yaml"
    policy_file.write_text(
        """
rules: []
""",
        encoding="utf-8",
    )

    evaluation_result = RuleEvaluationResult(matched_rule=None)

    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        mock_runtime.return_value.run_once.return_value = evaluation_result

        result = runner.invoke(
            app,
            [
                "policy",
                "run",
                "--once",
                "--policy",
                str(policy_file),
            ],
        )

    assert result.exit_code == 0
    assert "No rule matched" in result.stdout
    mock_runtime.return_value.run_once.assert_called_once_with(
        configuration_path=policy_file, dry_run=False
    )


def test_cli_policy_run_calls_run_once() -> None:
    evaluation_result = RuleEvaluationResult(matched_rule=None)

    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        mock_runtime.return_value.run_once.return_value = evaluation_result

        result = runner.invoke(
            app,
            ["policy", "run", "--once"],
        )

    assert result.exit_code == 0
    assert "No rule matched" in result.stdout
    mock_runtime.return_value.run_once.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"), dry_run=False
    )
    mock_runtime.return_value.run_continuously.assert_not_called()


def test_cli_policy_run_calls_run_continuously() -> None:
    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        mock_runtime.return_value.run_continuously.return_value = iter([])

        result = runner.invoke(
            app,
            ["policy", "run"],
        )

    assert result.exit_code == 0
    mock_runtime.return_value.run_continuously.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"),
        stop_on_match=False,
        dry_run=False,
    )
    mock_runtime.return_value.run_once.assert_not_called()


def test_cli_policy_run_uses_custom_policy_path(tmp_path: Path) -> None:
    policy_file = tmp_path / "custom-policy.yaml"

    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        mock_runtime.return_value.run_continuously.return_value = iter([])

        result = runner.invoke(
            app,
            [
                "policy",
                "run",
                "--policy",
                str(policy_file),
            ],
        )

    assert result.exit_code == 0
    mock_runtime.return_value.run_continuously.assert_called_once_with(
        configuration_path=policy_file,
        stop_on_match=False,
        dry_run=False,
    )


def test_cli_policy_run_passes_stop_on_match() -> None:
    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        mock_runtime.return_value.run_continuously.return_value = iter([])

        result = runner.invoke(
            app,
            [
                "policy",
                "run",
                "--stop-on-match",
            ],
        )

    assert result.exit_code == 0
    mock_runtime.return_value.run_continuously.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"),
        stop_on_match=True,
        dry_run=False,
    )


def test_cli_policy_run_passes_custom_policy_and_stop_on_match(tmp_path: Path) -> None:
    policy_file = tmp_path / "custom-policy.yaml"

    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        mock_runtime.return_value.run_continuously.return_value = iter([])

        result = runner.invoke(
            app,
            [
                "policy",
                "run",
                "--policy",
                str(policy_file),
                "--stop-on-match",
            ],
        )

    assert result.exit_code == 0
    mock_runtime.return_value.run_continuously.assert_called_once_with(
        configuration_path=policy_file,
        stop_on_match=True,
        dry_run=False,
    )


def test_cli_policy_run_continuously_logs_triggered_match() -> None:
    rule = Rule(
        name="Test rule",
        condition=Dummy_Condition(given_result=True),
        action=ShutdownAction(Dummy_PowerProvider()),
    )

    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        mock_runtime.return_value.run_continuously.return_value = iter(
            [RuleEvaluationResult(matched_rule=rule, action_triggered=True)]
        )

        result = runner.invoke(
            app,
            ["policy", "run", "--stop-on-match"],
        )

    assert result.exit_code == 0
    assert "Rule 'Test rule' matched, executed action: shutdown" in result.stdout


def test_cli_policy_run_continuously_logs_dry_run_match() -> None:
    rule = Rule(
        name="Test rule",
        condition=Dummy_Condition(given_result=True),
        action=ShutdownAction(Dummy_PowerProvider()),
    )

    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        mock_runtime.return_value.run_continuously.return_value = iter(
            [RuleEvaluationResult(matched_rule=rule, action_triggered=True)]
        )

        result = runner.invoke(
            app,
            ["policy", "run", "--dry-run", "--stop-on-match"],
        )

    assert result.exit_code == 0
    assert (
        "[DRY RUN] Rule 'Test rule' matched, would have executed action: shutdown"
        in result.stdout
    )
    mock_runtime.return_value.run_continuously.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"),
        stop_on_match=True,
        dry_run=True,
    )


def test_cli_policy_run_continuously_logs_stopping_evaluation_on_stop_on_match() -> (
    None
):
    rule = Rule(
        name="Test rule",
        condition=Dummy_Condition(given_result=True),
        action=ShutdownAction(Dummy_PowerProvider()),
    )

    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        mock_runtime.return_value.run_continuously.return_value = iter(
            [RuleEvaluationResult(matched_rule=rule, action_triggered=True)]
        )

        result = runner.invoke(
            app,
            ["policy", "run", "--stop-on-match"],
        )

    assert result.exit_code == 0
    assert "Rule matched, stopping evaluation" in result.stdout


def test_cli_policy_run_continuously_does_not_log_when_no_match() -> None:
    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        mock_runtime.return_value.run_continuously.return_value = iter(
            [RuleEvaluationResult(matched_rule=None, action_triggered=False)]
        )

        result = runner.invoke(
            app,
            ["policy", "run", "--stop-on-match"],
        )

    assert result.exit_code == 0
    assert "matched" not in result.stdout


def test_cli_policy_run_continuously_does_not_log_repeated_match() -> None:
    rule = Rule(
        name="Test rule",
        condition=Dummy_Condition(given_result=True),
        action=ShutdownAction(Dummy_PowerProvider()),
    )

    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        mock_runtime.return_value.run_continuously.return_value = iter(
            [
                RuleEvaluationResult(matched_rule=rule, action_triggered=True),
                # Second evaluation: same rule still matches, but the action was
                # already triggered before, so it should not be logged again
                RuleEvaluationResult(matched_rule=rule, action_triggered=False),
            ]
        )

        result = runner.invoke(
            app,
            ["policy", "run"],
        )

    assert result.exit_code == 0
    assert result.stdout.count("matched, executed action") == 1
