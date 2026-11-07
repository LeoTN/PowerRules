import logging
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape

from powerrules.application.logging import LogLevel, configure_logging, console
from powerrules.application.runtime import (
    DEFAULT_EVALUATION_INTERVAL_SECONDS,
    PowerRulesRuntime,
    describe_actions,
    validate_evaluation_interval,
)
from powerrules.application.trust import find_stale_entries, trust_policy
from powerrules.cli.errors import cli_command
from powerrules.cli.trust_output import (
    create_trust_checker,
    print_trust_reports,
    report_trust,
)
from powerrules.config.loader import ConfigurationLoader
from powerrules.platform.clock import SystemClockProvider
from powerrules.trust.report import build_entry_report
from powerrules.trust.store import (
    TrustStatus,
    TrustStore,
)

logger = logging.getLogger(__name__)

DEFAULT_POLICY_PATH = Path("powerrules.yaml")
DEFAULT_LOG_LEVEL = LogLevel.INFO
DEFAULT_LOG_FILE_PATH = Path("powerrules.log")

# The policy option is shared by all commands which work with a policy file
PolicyOption = Annotated[
    Path,
    typer.Option(
        "--policy",
        "-p",
        help="Path to the PowerRules policy file.",
    ),
]

# Logging options are defined on the root command, so they apply to every subcommand
LogLevelOption = Annotated[
    LogLevel,
    typer.Option(
        "--log-level",
        help="Minimum log level shown on the console and written to the log file.",
    ),
]

LogFileOption = Annotated[
    Path,
    typer.Option(
        "--log-file",
        help="Path to the rotating log file.",
    ),
]

LogLevelFileOption = Annotated[
    LogLevel | None,
    typer.Option(
        "--log-level-file",
        help="Minimum log level written to the log file. Defaults to --log-level if not set.",
    ),
]


# Main application
app = typer.Typer(
    name="pwru",
    help="A rule-based command automation tool.",
    no_args_is_help=True,
)

# Policy subcommand
policy_app = typer.Typer(
    name="policy",
    help="Manage PowerRules policies.",
    no_args_is_help=True,
)

# Trust subcommand
trust_app = typer.Typer(
    name="trust",
    help="Manage which policies are trusted.",
    no_args_is_help=True,
)

app.add_typer(policy_app, name="policy")
app.add_typer(trust_app, name="trust")


def version_callback(value: bool) -> None:
    """Display PowerRules version and exit."""
    if value:
        # The number is highlighted incorrectly and markup is disabled because it's not needed
        console.print(
            f"PowerRules {version('powerrules')}", markup=False, highlight=False
        )
        raise typer.Exit()


def interval_callback(value: float) -> float:
    """Validate the evaluation interval and report an invalid one as a usage error.

    Args:
        value: Interval in seconds given on the command line.

    Returns:
        The unchanged interval.

    Raises:
        typer.BadParameter: If the interval is not usable, which results in exit code 2.
    """
    try:
        validate_evaluation_interval(value)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e

    return value


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Display PowerRules version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """A rule-based command automation tool."""


@policy_app.command("validate")
@cli_command
def validate(
    policy: PolicyOption = DEFAULT_POLICY_PATH,
    log_level: LogLevelOption = DEFAULT_LOG_LEVEL,
    log_file: LogFileOption = DEFAULT_LOG_FILE_PATH,
    log_level_file: LogLevelFileOption = None,
) -> None:
    """Validate a PowerRules policy file."""
    configure_logging(
        console_level=log_level, log_file=log_file, file_level=log_level_file
    )

    # Validating is the step before trusting a policy, so an untrusted policy is only reported as a warning
    ConfigurationLoader(
        trust_checker=create_trust_checker(False, False, always_show_table=True)
    ).load(policy)

    # Theoretically, one could inject markdown via the file path
    console.print(f"Policy '{policy}' is valid", markup=False)


@policy_app.command("show")
@cli_command
def show(
    policy: PolicyOption = DEFAULT_POLICY_PATH,
    log_level: LogLevelOption = DEFAULT_LOG_LEVEL,
    log_file: LogFileOption = DEFAULT_LOG_FILE_PATH,
    log_level_file: LogLevelFileOption = None,
) -> None:
    """Display the configured rules of a PowerRules policy."""
    configure_logging(
        console_level=log_level, log_file=log_file, file_level=log_level_file
    )

    policy_configuration = ConfigurationLoader().load(policy)

    for index, rule in enumerate(policy_configuration.rules, start=1):
        # Show enabled or disabled status with colors
        status_style = "green" if rule.enabled else "red"
        status_text = "enabled" if rule.enabled else "disabled"
        # Escape the rule name because it might contain markup
        console.print(
            f"{index}. {escape(rule.name)} [{status_style}]\\[{status_text}][/{status_style}]"
        )


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
    no_require_trust: bool = typer.Option(
        False,
        "--no-require-trust",
        help="Run the policy even if it is not trusted or was modified since it was trusted (see 'trust add').",
    ),
    interval: float = typer.Option(
        DEFAULT_EVALUATION_INTERVAL_SECONDS,
        "--interval",
        help="Seconds between the starts of two evaluations. Has no effect together with --once.",
        callback=interval_callback,
    ),
    policy: PolicyOption = DEFAULT_POLICY_PATH,
    log_level: LogLevelOption = DEFAULT_LOG_LEVEL,
    log_file: LogFileOption = DEFAULT_LOG_FILE_PATH,
    log_level_file: LogLevelFileOption = None,
) -> None:
    """Evaluate a PowerRules policy continuously or once."""
    configure_logging(
        console_level=log_level, log_file=log_file, file_level=log_level_file
    )

    # Commands of actions are only executed without a dry run, commands of conditions are always executed
    runtime = PowerRulesRuntime(
        trust_checker=create_trust_checker(
            require_trust_for_actions=not dry_run and not no_require_trust,
            require_trust_for_conditions=not no_require_trust,
        )
    )

    if once:
        logger.info(f"Running policy '{policy}' once...")
        result = runtime.run_once(configuration_path=policy, dry_run=dry_run)

        if result.matched_rule is None:
            logger.info("No rule matched")
        elif dry_run:
            logger.info(
                f"[DRY RUN] Rule '{result.matched_rule.name}' matched, would have executed actions: {describe_actions(result.matched_rule)}"
            )
        # Technically, the system could already be shut down at this point, but this usually takes a few seconds
        else:
            logger.info(
                f"Rule '{result.matched_rule.name}' matched, executed actions: {describe_actions(result.matched_rule)}"
            )

        return

    logger.info(f"Running policy '{policy}' continuously...")

    for result in runtime.run_continuously(
        configuration_path=policy,
        evaluation_interval=interval,
        stop_on_match=stop_on_match,
        dry_run=dry_run,
    ):
        if not result.action_triggered:
            continue

        assert result.matched_rule is not None  # action_triggered implies a match

        if dry_run:
            logger.info(
                f"[DRY RUN] Rule '{result.matched_rule.name}' matched, would have executed actions: {describe_actions(result.matched_rule)}"
            )
        # Technically, the system could already be shut down at this point, but this usually takes a few seconds
        else:
            logger.info(
                f"Rule '{result.matched_rule.name}' matched, executed actions: {describe_actions(result.matched_rule)}"
            )

        if stop_on_match:
            logger.info("Rule matched, stopping evaluation")


@trust_app.command("add")
@cli_command
def trust_add(
    policy: PolicyOption = DEFAULT_POLICY_PATH,
    log_level: LogLevelOption = DEFAULT_LOG_LEVEL,
    log_file: LogFileOption = DEFAULT_LOG_FILE_PATH,
    log_level_file: LogLevelFileOption = None,
) -> None:
    """Trust a PowerRules policy file, so modifications of it can be detected."""
    configure_logging(
        console_level=log_level, log_file=log_file, file_level=log_level_file
    )

    report = trust_policy(policy, TrustStore(), SystemClockProvider())

    console.print(f"Policy '{policy}' is now trusted", markup=False)
    report_trust(report, always_show_table=True)


@trust_app.command("remove")
@cli_command
def trust_remove(
    policy: PolicyOption = DEFAULT_POLICY_PATH,
    log_level: LogLevelOption = DEFAULT_LOG_LEVEL,
    log_file: LogFileOption = DEFAULT_LOG_FILE_PATH,
    log_level_file: LogLevelFileOption = None,
) -> None:
    """Remove the trust of a PowerRules policy file."""
    configure_logging(
        console_level=log_level, log_file=log_file, file_level=log_level_file
    )

    if TrustStore().untrust([policy]):
        console.print(f"Policy '{policy}' is no longer trusted", markup=False)
    else:
        console.print(f"Policy '{policy}' was not trusted", markup=False)


@trust_app.command("list")
@cli_command
def trust_list(
    trusted: bool = typer.Option(
        False,
        "--trusted",
        help="Only show policies for which the policy and all trusted files are trusted.",
    ),
    modified: bool = typer.Option(
        False,
        "--modified",
        help="Only show policies with a modified policy or trusted file.",
    ),
    missing: bool = typer.Option(
        False,
        "--missing",
        help="Only show policies with a missing policy or trusted file.",
    ),
    log_level: LogLevelOption = DEFAULT_LOG_LEVEL,
    log_file: LogFileOption = DEFAULT_LOG_FILE_PATH,
    log_level_file: LogLevelFileOption = None,
) -> None:
    """List all trusted policies and show their current trust status.

    Several filters can be combined, a policy is shown if it matches at least one of them.
    """
    configure_logging(
        console_level=log_level, log_file=log_file, file_level=log_level_file
    )

    entries = TrustStore().list_entries()

    if not entries:
        console.print("No policies are trusted")

        return

    reports = [build_entry_report(entry) for entry in entries]
    selected_statuses = [
        status
        for status, is_selected in (
            (TrustStatus.TRUSTED, trusted),
            (TrustStatus.MODIFIED, modified),
            (TrustStatus.MISSING, missing),
        )
        if is_selected
    ]

    if selected_statuses:
        reports = [
            report
            for report in reports
            if any(report.has_status(status) for status in selected_statuses)
        ]

        if not reports:
            console.print("No trusted policies match the selected filters")

            return

    print_trust_reports(reports)


def _format_policy_count(count: int) -> str:
    """Return the count with the matching singular or plural of "policy"."""
    return f"{count} {'policy' if count == 1 else 'policies'}"


@trust_app.command("prune")
@cli_command
def trust_prune(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Only show which trusted policies would be removed.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Remove the policies without asking for confirmation.",
    ),
    log_level: LogLevelOption = DEFAULT_LOG_LEVEL,
    log_file: LogFileOption = DEFAULT_LOG_FILE_PATH,
    log_level_file: LogLevelFileOption = None,
) -> None:
    """Remove trusted policies whose policy file no longer exists."""
    configure_logging(
        console_level=log_level, log_file=log_file, file_level=log_level_file
    )

    trust_store = TrustStore()
    stale_entries = find_stale_entries(trust_store)

    if not stale_entries:
        console.print("Nothing to prune")

        return

    print_trust_reports([build_entry_report(entry) for entry in stale_entries])

    count = _format_policy_count(len(stale_entries))

    if dry_run:
        console.print(f"[DRY RUN] Would remove {count}", markup=False)

        return

    if not yes:
        typer.confirm(f"Remove {count} from the trust store?", abort=True)

    trust_store.untrust(Path(entry.path) for entry in stale_entries)

    console.print(f"Removed {count} from the trust store")
