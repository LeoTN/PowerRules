import logging
from pathlib import Path

import pytest

from powerrules.application.invocation import build_trust_command
from powerrules.cli.trust_output import (
    create_trust_checker,
    print_trust_report,
    print_trust_reports,
    report_trust,
)
from powerrules.trust.report import TrustReport, TrustReportEntry
from powerrules.trust.store import TrustStatus, TrustStore
from tests.factories import make_trust_report
from tests.helpers import TRUSTED_AT, get_log_records

LOGGER_NAME = "powerrules.cli.trust_output"
_TRUSTED_AT_FORMAT = "%Y-%m-%d %H:%M"


####################
# report_trust tests
####################


def test_report_trust_logs_trusted_report_on_console_without_table(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    report_trust(make_trust_report("/policies/a.yaml", TrustStatus.TRUSTED))

    records = get_log_records(caplog, LOGGER_NAME)

    assert [record.levelno for record in records] == [logging.INFO, logging.INFO]
    # Without a table the messages are the only feedback, so they are shown on the console
    assert not any(getattr(record, "file_only", False) for record in records)
    assert "Trust status" not in capsys.readouterr().out


def test_report_trust_shows_table_and_logs_only_to_file_if_something_is_not_trusted(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    report_trust(make_trust_report("/policies/a.yaml", TrustStatus.MODIFIED))

    records = get_log_records(caplog, LOGGER_NAME)

    assert [record.levelno for record in records] == [logging.INFO, logging.WARNING]
    assert all(getattr(record, "file_only", False) for record in records)
    assert "Trust status" in capsys.readouterr().out


def test_report_trust_can_always_show_table(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    report_trust(make_trust_report("/policies/a.yaml"), always_show_table=True)

    assert all(
        getattr(record, "file_only", False)
        for record in get_log_records(caplog, LOGGER_NAME)
    )
    assert "Trust status" in capsys.readouterr().out


def test_report_trust_logs_description_of_every_entry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    report = make_trust_report("/policies/a.yaml", TrustStatus.UNKNOWN)

    report_trust(report)

    assert [record.getMessage() for record in get_log_records(caplog, LOGGER_NAME)] == [
        entry.describe() for entry in report.entries
    ]


####################
# table output tests
####################


def test_print_trust_reports_shows_columns_and_all_policies(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_trust_reports(
        [
            make_trust_report("/policies/a.yaml", TrustStatus.TRUSTED),
            make_trust_report(
                "/policies/b.yaml",
                TrustStatus.MODIFIED,
                policy_status=TrustStatus.UNKNOWN,
            ),
        ]
    )

    output = capsys.readouterr().out

    for text in ("Status", "Trusted at", "Path", "unknown", "modified"):
        assert text in output

    for path in ("/policies/a.yaml", "/policies/b.yaml", "/policies/b.yaml.file0"):
        assert str(Path(path)) in output


def test_print_trust_reports_shows_trusted_time_only_for_policies(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_trust_reports(
        [
            make_trust_report(
                "/policies/a.yaml", TrustStatus.TRUSTED, TrustStatus.TRUSTED
            ),
            make_trust_report("/policies/b.yaml", TrustStatus.TRUSTED),
        ]
    )

    assert capsys.readouterr().out.count(TRUSTED_AT.strftime(_TRUSTED_AT_FORMAT)) == 2


def test_print_trust_reports_leaves_time_empty_for_policy_which_was_never_trusted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_trust_report(
        make_trust_report(policy_status=TrustStatus.UNKNOWN, trusted_at=None)
    )

    assert "2026" not in capsys.readouterr().out


def test_print_trust_report_shows_reason_why_a_file_cannot_be_read(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = TrustReport(
        (
            TrustReportEntry(Path("/policies/a.yaml"), TrustStatus.TRUSTED, True),
            TrustReportEntry(
                Path("/policies/a.sh"), TrustStatus.MISSING, detail="Test reason"
            ),
        )
    )

    print_trust_report(report)

    output = capsys.readouterr().out

    assert "missing" in output
    assert "Test reason" in output


def test_print_trust_report_does_not_interpret_paths_as_markup(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_trust_report(
        TrustReport(
            (
                TrustReportEntry(
                    Path("/policies/[red]a[/red].yaml"),
                    TrustStatus.TRUSTED,
                    is_policy=True,
                ),
            )
        )
    )

    assert "[red]a[\\red]" in capsys.readouterr().out


############################
# create_trust_checker tests
############################


@pytest.mark.parametrize("require_trust", [True, False])
def test_create_trust_checker_uses_trust_store_and_command_builder(
    require_trust: bool,
) -> None:
    checker = create_trust_checker(require_trust)

    assert checker.require_trust is require_trust
    assert isinstance(checker.trust_store, TrustStore)
    assert checker.trust_command_builder is build_trust_command
    assert checker.reporter is not None


def test_create_trust_checker_reporter_shows_table_if_requested(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checker = create_trust_checker(False, always_show_table=True)

    assert checker.reporter is not None

    checker.reporter(make_trust_report())

    assert "Trust status" in capsys.readouterr().out
