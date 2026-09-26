from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from powerrules.application.runtime import PowerRulesRuntime, describe_action
from powerrules.cli.errors import cli_command
from powerrules.config.loader import ConfigurationLoader

DEFAULT_POLICY_PATH = Path("powerrules.yaml")

# The policy option is shared by all commands which work with a policy file
PolicyOption = Annotated[
    Path,
    typer.Option(
        "--policy",
        "-p",
        help="Path to the PowerRules policy file.",
    ),
]

# Main application
app = typer.Typer(
    name="pwru",
    help="A rule-based computer power state management tool.",
    no_args_is_help=True,
)

# Policy subcommand
policy_app = typer.Typer(
    name="policy",
    help="Manage PowerRules policies.",
    no_args_is_help=True,
)

app.add_typer(policy_app, name="policy")


def version_callback(value: bool) -> None:
    """Display the installed PowerRules version."""
    if value:
        typer.echo(f"PowerRules {version('powerrules')}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Display the installed PowerRules version.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """A rule-based computer power state management tool."""


@policy_app.command("validate")
@cli_command
def validate(
    policy: PolicyOption = DEFAULT_POLICY_PATH,
) -> None:
    """Validate a PowerRules policy file."""
    ConfigurationLoader().load(policy)

    typer.echo("[INFO] Policy is valid")


@policy_app.command("show")
@cli_command
def show(
    policy: PolicyOption = DEFAULT_POLICY_PATH,
) -> None:
    """Display the configured rules of a PowerRules policy."""
    policy_configuration = ConfigurationLoader().load(policy)

    for index, rule in enumerate(policy_configuration.rules, start=1):
        status = "enabled" if rule.enabled else "disabled"
        typer.echo(f"{index}. {rule.name} [{status}]")


@policy_app.command("run")
@cli_command
def run(
    once: bool = typer.Option(
        False,
        "--once",
        help="Evaluate the policy once and then exit.",
    ),
    stop_on_match: bool = typer.Option(
        False,
        "--stop-on-match",
        help="Stop the continuous evaluation after the first rule match.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Evaluate the policy without executing any matching action.",
    ),
    policy: PolicyOption = DEFAULT_POLICY_PATH,
) -> None:
    """Evaluate a PowerRules policy continuously or once."""
    runtime = PowerRulesRuntime()

    if once:
        typer.echo(f"[INFO] Running policy '{policy}' once...")
        result = runtime.run_once(configuration_path=policy, dry_run=dry_run)

        if result.matched_rule is None:
            typer.echo("[INFO] No rule matched")
        elif dry_run:
            typer.echo(
                f"[INFO] [DRY RUN] Rule '{result.matched_rule.name}' matched, would have executed action: {describe_action(result.matched_rule.action)}"
            )
        # Technically, the system could already be shut down at this point, but this usually takes a few seconds
        else:
            typer.echo(
                f"[INFO] Rule '{result.matched_rule.name}' matched, executed action: {describe_action(result.matched_rule.action)}"
            )

        return

    typer.echo(f"[INFO] Running policy '{policy}' continuously...")

    for result in runtime.run_continuously(
        configuration_path=policy,
        stop_on_match=stop_on_match,
        dry_run=dry_run,
    ):
        if not result.action_triggered:
            continue

        assert result.matched_rule is not None  # action_triggered implies a match

        if dry_run:
            typer.echo(
                f"[INFO] [DRY RUN] Rule '{result.matched_rule.name}' matched, would have executed action: {describe_action(result.matched_rule.action)}"
            )
        # Technically, the system could already be shut down at this point, but this usually takes a few seconds
        else:
            typer.echo(
                f"[INFO] Rule '{result.matched_rule.name}' matched, executed action: {describe_action(result.matched_rule.action)}"
            )

        if stop_on_match:
            typer.echo("[INFO] Rule matched, stopping evaluation")
