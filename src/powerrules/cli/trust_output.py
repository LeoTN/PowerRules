import logging
from collections.abc import Sequence
from functools import partial

from rich import box
from rich.table import Table
from rich.text import Text

from powerrules.application.invocation import build_trust_command
from powerrules.application.logging import FILE_ONLY_EXTRA, console
from powerrules.trust.checker import PolicyTrustChecker
from powerrules.trust.report import TrustReport
from powerrules.trust.store import TrustStatus, TrustStore

logger = logging.getLogger(__name__)

_TRUST_STATUS_STYLES = {
    TrustStatus.TRUSTED: "green",
    TrustStatus.UNKNOWN: "yellow",
    TrustStatus.MODIFIED: "red",
    TrustStatus.MISSING: "red",
}
_TRUSTED_AT_FORMAT = "%Y-%m-%d %H:%M"


def _get_branch(is_last: bool) -> str:
    """Return the tree branch in front of a trusted file. Alternatively, an ASCII fallback for consoles without UTF-8."""
    if console.options.ascii_only:
        return "`- " if is_last else "|- "

    return "└─ " if is_last else "├─ "


def print_trust_reports(reports: Sequence[TrustReport]) -> None:
    """Print the trust status of one or more policies and their trusted files as a single table.

    Each policy is shown in bold with its trusted files below it, policies are separated by a line.

    Args:
        reports: The reports to print.
    """
    table = Table(
        title="Trust status",
        title_justify="left",
        title_style="bold",
        header_style="bold",
        box=box.HORIZONTALS,
        pad_edge=False,
    )
    table.add_column("Status")
    table.add_column("Trusted at")
    # Paths are folded instead of truncated, so the full path always stays visible
    table.add_column("Path", overflow="fold")

    for index, report in enumerate(reports):
        if index > 0:
            table.add_section()

        last_index = len(report.entries) - 1

        for entry_index, entry in enumerate(report.entries):
            # Text objects are used on purpose, so paths are never interpreted as markup
            path = Text()

            if entry.is_policy:
                path.append(str(entry.path), style="bold")
            else:
                path.append(
                    _get_branch(entry_index == last_index), style="bright_black"
                )
                path.append(str(entry.path))

            # The reason why a file cannot be read
            if entry.detail:
                path.append(f"\n{entry.detail}", style="bright_black")

            table.add_row(
                Text(entry.status.value, style=_TRUST_STATUS_STYLES[entry.status]),
                entry.trusted_at.strftime(_TRUSTED_AT_FORMAT)
                if entry.trusted_at
                else "",
                path,
            )

    console.print()
    console.print(table)


def print_trust_report(report: TrustReport) -> None:
    """Print the trust status and the full path of the policy and each of its trusted files as a table.

    Args:
        report: The report to print.
    """
    print_trust_reports([report])


def report_trust(report: TrustReport, always_show_table: bool = False) -> None:
    """Log the trust status of the policy and its trusted files and show the table if needed.

    The table is only shown if something is not trusted or if it is requested explicitly.
    If it is shown, the messages are only written to the log file, because the table already contains the same information.

    Args:
        report: The report to log and show.
        always_show_table: Show the table even if everything is trusted.
    """
    show_table = always_show_table or not report.is_trusted
    extra = FILE_ONLY_EXTRA if show_table else None

    for entry in report.entries:
        level = logging.INFO if entry.status is TrustStatus.TRUSTED else logging.WARNING
        logger.log(level, entry.describe(), extra=extra)

    if show_table:
        print_trust_report(report)


def create_trust_checker(
    require_trust: bool, always_show_table: bool = False
) -> PolicyTrustChecker:
    """Create a checker which verifies policies against the trust store of the current user and reports the result."""
    return PolicyTrustChecker(
        TrustStore(),
        require_trust=require_trust,
        reporter=partial(report_trust, always_show_table=always_show_table),
        trust_command_builder=build_trust_command,
    )
