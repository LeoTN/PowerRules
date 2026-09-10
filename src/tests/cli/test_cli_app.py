import re
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from powerrules.cli.app import app
from powerrules.engine.models import Rule, RuleEvaluationResult
from tests.dummies import Dummy_Action, Dummy_Condition

runner = CliRunner()


def test_cli_displays_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "A rule-based computer power state management tool" in result.stdout


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    # Check if the version matches a valid format
    assert re.fullmatch(
        r"PowerRules \d+\.\d+\.\d+(?:b\d+)?",
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
    assert "[INFO] Policy is valid" in result.stdout


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
    assert "[INFO] Rule 'Test rule' matched" in result.stdout
    mock_runtime.return_value.run_once.assert_called_once_with(
        configuration_path=Path("powerrules.yaml")
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
    assert "[INFO] No rule matched" in result.stdout
    mock_runtime.return_value.run_once.assert_called_once_with(
        configuration_path=Path("powerrules.yaml")
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
    assert "[INFO] No rule matched" in result.stdout
    mock_runtime.return_value.run_once.assert_called_once_with(
        configuration_path=policy_file
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
    assert "[INFO] No rule matched" in result.stdout
    mock_runtime.return_value.run_once.assert_called_once_with(
        configuration_path=Path("powerrules.yaml")
    )
    mock_runtime.return_value.run_continuously.assert_not_called()


def test_cli_policy_run_calls_run_continuously() -> None:
    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
        result = runner.invoke(
            app,
            ["policy", "run"],
        )

    assert result.exit_code == 0
    mock_runtime.return_value.run_continuously.assert_called_once_with(
        configuration_path=Path("powerrules.yaml"),
        stop_on_match=False,
    )
    mock_runtime.return_value.run_once.assert_not_called()


def test_cli_policy_run_uses_custom_policy_path(tmp_path: Path) -> None:
    policy_file = tmp_path / "custom-policy.yaml"

    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
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
    )


def test_cli_policy_run_passes_stop_on_match() -> None:
    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
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
    )


def test_cli_policy_run_passes_custom_policy_and_stop_on_match(tmp_path: Path) -> None:
    policy_file = tmp_path / "custom-policy.yaml"

    with patch("powerrules.cli.app.PowerRulesRuntime") as mock_runtime:
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
    )
