import logging
from functools import partial
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from powerrules.application.invocation import build_trust_command
from powerrules.application.logging import LogLevel, configure_logging, console
from powerrules.application.runtime import (
    PowerRulesRuntime,
    describe_actions,
)
from powerrules.cli.errors import cli_command
from powerrules.config.loader import ConfigurationLoader
from powerrules.platform.clock import SystemClockProvider
from powerrules.trust.checker import PolicyTrustChecker
from powerrules.trust.report import TrustReport, build_trust_report
from powerrules.trust.store import (
    TrustStatus,
    TrustStore,
    compute_digest,
    compute_trusted_file_digests,
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

_TRUST_STATUS_STYLES = {
    TrustStatus.TRUSTED: "green",
    TrustStatus.UNKNOWN: "yellow",
    TrustStatus.MODIFIED: "red",
    TrustStatus.MISSING: "red",
}


def print_trust_report(report: TrustReport) -> None:
    """Print the trust status and the full path of the policy and each of its trusted files as a table.

    Args:
        report: The report to print.
    """
    table = Table(
        title="Trust status",
        title_justify="left",
        box=box.SIMPLE_HEAD,
        pad_edge=False,
    )
    table.add_column("Status")
    # Paths are folded instead of truncated, so the full path always stays visible
    table.add_column("Path", overflow="fold")

    for entry in report.entries:
        # Text objects are used on purpose, so paths are never interpreted as markup
        path = Text(str(entry.path))

        # The reason why a file cannot be read
        if entry.detail:
            path.append(f"\n{entry.detail}", style="bright_black")

        table.add_row(
            Text(entry.status.value, style=_TRUST_STATUS_STYLES[entry.status]),
            path,
        )

    console.print()
    console.print(table)


def report_trust(report: TrustReport, always_show_table: bool = False) -> None:
    """Log the trust status of the policy and its trusted files and show the table if needed.

    The table is only shown if something is not trusted or if it is requested explicitly.

    Args:
        report: The report to log and show.
        always_show_table: Show the table even if everything is trusted.
    """
    for entry in report.entries:
        level = logging.INFO if entry.status is TrustStatus.TRUSTED else logging.WARNING
        logger.log(level, entry.describe())

    if always_show_table or not report.is_trusted:
        print_trust_report(report)


def _create_trust_checker(
    require_trust: bool, always_show_table: bool = False
) -> PolicyTrustChecker:
    """Create a checker which verifies policies against the trust store of the current user and reports the result."""
    return PolicyTrustChecker(
        TrustStore(),
        require_trust=require_trust,
        reporter=partial(report_trust, always_show_table=always_show_table),
        trust_command_builder=build_trust_command,
    )


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

app.add_typer(policy_app, name="policy")


def version_callback(value: bool) -> None:
    """Display PowerRules version and exit."""
    if value:
        # The number is highlighted incorrectly and markup is disabled because it's not needed
        console.print(
            f"PowerRules {version('powerrules')}", markup=False, highlight=False
        )
        raise typer.Exit()


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
        trust_checker=_create_trust_checker(False, always_show_table=True)
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
        help="Run the policy even if it is not trusted or was modified since it was trusted (see 'policy trust').",
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

    # Commands are only executed without a dry run, so trust is only required then
    runtime = PowerRulesRuntime(
        trust_checker=_create_trust_checker(not dry_run and not no_require_trust)
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


@policy_app.command("trust")
@cli_command
def trust(
    policy: PolicyOption = DEFAULT_POLICY_PATH,
    log_level: LogLevelOption = DEFAULT_LOG_LEVEL,
    log_file: LogFileOption = DEFAULT_LOG_FILE_PATH,
    log_level_file: LogLevelFileOption = None,
) -> None:
    """Trust a PowerRules policy file, so modifications of it can be detected."""
    configure_logging(
        console_level=log_level, log_file=log_file, file_level=log_level_file
    )

    # Resolve symbolic links once, so the validated, hashed and trusted file is the same one
    resolved_policy = policy.resolve()
    content = resolved_policy.read_bytes()
    # An invalid policy must not be trusted
    configuration = ConfigurationLoader().parse(content)
    digest = compute_digest(content)
    trusted_files = compute_trusted_file_digests(
        resolved_policy.parent, configuration.get_trusted_files()
    )

    trust_store = TrustStore()
    trust_store.trust(
        resolved_policy, digest, SystemClockProvider().now(), trusted_files
    )

    console.print(f"Policy '{policy}' is now trusted", markup=False)
    # Read back from the store, so the output shows what was actually saved
    report_trust(
        build_trust_report(
            resolved_policy,
            digest,
            trust_store.get_entry(resolved_policy),
            trusted_files,
        ),
        always_show_table=True,
    )


@policy_app.command("untrust")
@cli_command
def untrust(
    policy: PolicyOption = DEFAULT_POLICY_PATH,
    log_level: LogLevelOption = DEFAULT_LOG_LEVEL,
    log_file: LogFileOption = DEFAULT_LOG_FILE_PATH,
    log_level_file: LogLevelFileOption = None,
) -> None:
    """Remove the trust of a PowerRules policy file."""
    configure_logging(
        console_level=log_level, log_file=log_file, file_level=log_level_file
    )

    if TrustStore().untrust(policy):
        console.print(f"Policy '{policy}' is no longer trusted", markup=False)
    else:
        console.print(f"Policy '{policy}' was not trusted", markup=False)


@policy_app.command("list-trusted")
@cli_command
def list_trusted(
    log_level: LogLevelOption = DEFAULT_LOG_LEVEL,
    log_file: LogFileOption = DEFAULT_LOG_FILE_PATH,
    log_level_file: LogLevelFileOption = None,
) -> None:
    """List all trusted PowerRules policy files."""
    configure_logging(
        console_level=log_level, log_file=log_file, file_level=log_level_file
    )

    entries = TrustStore().list_entries()

    if not entries:
        console.print("No policies are trusted")

        return

    for entry in entries:
        console.print(f"{entry.digest}  {entry.path}", markup=False, highlight=False)
