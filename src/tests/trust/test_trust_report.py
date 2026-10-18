from datetime import datetime
from pathlib import Path

import pytest

from powerrules.trust.report import (
    TrustReport,
    TrustReportEntry,
    build_entry_report,
    build_trust_report,
    check_file,
)
from powerrules.trust.store import (
    TrustedFileEntry,
    TrustEntry,
    TrustStatus,
    compute_file_digest,
    make_path_key,
)

TRUSTED_AT = datetime(2026, 10, 17, 14, 3)


def _write(path: Path, content: str = "content") -> Path:
    """Write a file and return its resolved path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    return path.resolve()


def _make_trusted_files(*files: Path) -> dict[str, TrustedFileEntry]:
    """Trust the current content of the files."""
    return {
        make_path_key(file): TrustedFileEntry(
            path=str(file), digest=compute_file_digest(file)
        )
        for file in files
    }


def _make_entry(policy: Path, *files: Path) -> TrustEntry:
    """Create the entry of a policy which is trusted with its current content."""
    return TrustEntry(
        path=str(policy),
        digest=compute_file_digest(policy),
        trusted_at=TRUSTED_AT,
        trusted_files=_make_trusted_files(*files),
    )


def _get_statuses(report: TrustReport) -> list[TrustStatus]:
    return [entry.status for entry in report.entries]


@pytest.fixture
def policy(tmp_path: Path) -> Path:
    return _write(tmp_path / "powerrules.yaml", "rules: []")


@pytest.fixture
def script(tmp_path: Path) -> Path:
    return _write(tmp_path / "scripts" / "backup.sh", "echo backup")


###################
# describe / report
###################


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (
            TrustReportEntry(Path("p.yaml"), TrustStatus.TRUSTED, is_policy=True),
            "Policy 'p.yaml' is trusted",
        ),
        (
            TrustReportEntry(Path("a.sh"), TrustStatus.UNKNOWN),
            "File 'a.sh' is not trusted yet",
        ),
        (
            TrustReportEntry(Path("a.sh"), TrustStatus.MODIFIED),
            "File 'a.sh' was modified since it was trusted",
        ),
        (
            TrustReportEntry(Path("a.sh"), TrustStatus.MISSING, detail="No such file"),
            "File 'a.sh' cannot be read: No such file",
        ),
        (
            TrustReportEntry(Path("p.yaml"), TrustStatus.MISSING, is_policy=True),
            "Policy 'p.yaml' cannot be read",
        ),
    ],
)
def test_trust_report_entry_describes_status(
    entry: TrustReportEntry, expected: str
) -> None:
    assert entry.describe() == expected


def test_trust_report_is_trusted_only_if_every_entry_is_trusted() -> None:
    trusted = TrustReportEntry(Path("a"), TrustStatus.TRUSTED)

    assert TrustReport((trusted, trusted)).is_trusted is True

    for status in (TrustStatus.UNKNOWN, TrustStatus.MODIFIED, TrustStatus.MISSING):
        assert (
            TrustReport((trusted, TrustReportEntry(Path("b"), status))).is_trusted
            is False
        )


##################
# check_file tests
##################


def test_check_file_reports_trusted_file(script: Path) -> None:
    assert check_file(script, _make_trusted_files(script)) == TrustReportEntry(
        script, TrustStatus.TRUSTED
    )


def test_check_file_reports_modified_file(script: Path) -> None:
    trusted_files = _make_trusted_files(script)
    script.write_text("echo changed", encoding="utf-8")

    assert check_file(script, trusted_files).status is TrustStatus.MODIFIED


def test_check_file_reports_unknown_file(script: Path) -> None:
    assert check_file(script, {}).status is TrustStatus.UNKNOWN


def test_check_file_reports_missing_file_with_reason(tmp_path: Path) -> None:
    missing = (tmp_path / "missing.sh").resolve()

    entry = check_file(missing, {})

    assert entry.status is TrustStatus.MISSING
    assert entry.path == missing
    assert entry.detail


def test_check_file_resolves_symbolic_links(tmp_path: Path, script: Path) -> None:
    link = tmp_path / "link.sh"

    try:
        link.symlink_to(script)
    except (OSError, NotImplementedError):
        pytest.skip("Symbolic links are not available")

    entry = check_file(link, _make_trusted_files(script))

    assert entry == TrustReportEntry(script, TrustStatus.TRUSTED)


def test_check_file_detects_link_which_points_to_another_file(
    tmp_path: Path, script: Path
) -> None:
    other = _write(tmp_path / "other.sh", "echo other")
    link = tmp_path / "link.sh"

    try:
        link.symlink_to(script)
    except (OSError, NotImplementedError):
        pytest.skip("Symbolic links are not available")

    trusted_files = _make_trusted_files(script)
    link.unlink()
    link.symlink_to(other)

    assert check_file(link, trusted_files).status is TrustStatus.UNKNOWN


##########################
# build_trust_report tests
##########################


def test_build_trust_report_lists_policy_first_and_files_in_order(
    tmp_path: Path, policy: Path, script: Path
) -> None:
    other = _write(tmp_path / "other.sh")
    entry = _make_entry(policy, script, other)

    report = build_trust_report(
        policy, compute_file_digest(policy), entry, (other, script)
    )

    assert [e.path for e in report.entries] == [policy, other, script]
    assert [e.is_policy for e in report.entries] == [True, False, False]


def test_build_trust_report_of_trusted_policy_and_files(
    policy: Path, script: Path
) -> None:
    entry = _make_entry(policy, script)

    report = build_trust_report(policy, compute_file_digest(policy), entry, (script,))

    assert report.is_trusted is True
    # Only the policy knows when it was trusted
    assert [e.trusted_at for e in report.entries] == [TRUSTED_AT, None]


def test_build_trust_report_of_policy_which_was_never_trusted(
    policy: Path, script: Path
) -> None:
    report = build_trust_report(policy, compute_file_digest(policy), None, (script,))

    assert _get_statuses(report) == [TrustStatus.UNKNOWN, TrustStatus.UNKNOWN]
    assert report.entries[0].trusted_at is None
    assert report.is_trusted is False


def test_build_trust_report_reports_modified_policy(policy: Path, script: Path) -> None:
    entry = _make_entry(policy, script)
    policy.write_text("rules: [] # changed", encoding="utf-8")

    report = build_trust_report(policy, compute_file_digest(policy), entry, (script,))

    assert _get_statuses(report) == [TrustStatus.MODIFIED, TrustStatus.TRUSTED]
    # The time of the former trust is still known
    assert report.entries[0].trusted_at == TRUSTED_AT


def test_build_trust_report_reports_modified_file(policy: Path, script: Path) -> None:
    entry = _make_entry(policy, script)
    script.write_text("echo changed", encoding="utf-8")

    report = build_trust_report(policy, compute_file_digest(policy), entry, (script,))

    assert _get_statuses(report) == [TrustStatus.TRUSTED, TrustStatus.MODIFIED]
    assert report.is_trusted is False


def test_build_trust_report_reports_file_which_was_added_after_trusting(
    tmp_path: Path, policy: Path, script: Path
) -> None:
    added = _write(tmp_path / "added.sh")
    entry = _make_entry(policy, script)

    report = build_trust_report(
        policy, compute_file_digest(policy), entry, (script, added)
    )

    assert _get_statuses(report) == [
        TrustStatus.TRUSTED,
        TrustStatus.TRUSTED,
        TrustStatus.UNKNOWN,
    ]


def test_build_trust_report_checks_every_file_even_after_a_problem(
    tmp_path: Path, policy: Path, script: Path
) -> None:
    missing = (tmp_path / "missing.sh").resolve()
    entry = _make_entry(policy, script)

    report = build_trust_report(
        policy, compute_file_digest(policy), entry, (missing, script)
    )

    assert _get_statuses(report) == [
        TrustStatus.TRUSTED,
        TrustStatus.MISSING,
        TrustStatus.TRUSTED,
    ]


def test_build_trust_report_without_files_only_contains_policy(policy: Path) -> None:
    report = build_trust_report(
        policy, compute_file_digest(policy), _make_entry(policy), ()
    )

    assert len(report.entries) == 1
    assert report.is_trusted is True


##########################
# build_entry_report tests
##########################


def test_build_entry_report_of_unchanged_entry_is_trusted(
    policy: Path, script: Path
) -> None:
    report = build_entry_report(_make_entry(policy, script))

    assert report.is_trusted is True
    assert [e.path for e in report.entries] == [policy, script]
    assert report.entries[0].is_policy is True
    assert report.entries[0].trusted_at == TRUSTED_AT


def test_build_entry_report_of_policy_without_files(policy: Path) -> None:
    assert len(build_entry_report(_make_entry(policy)).entries) == 1


def test_build_entry_report_reports_modified_policy_and_file(
    policy: Path, script: Path
) -> None:
    entry = _make_entry(policy, script)
    policy.write_text("rules: [] # changed", encoding="utf-8")
    script.write_text("echo changed", encoding="utf-8")

    assert _get_statuses(build_entry_report(entry)) == [
        TrustStatus.MODIFIED,
        TrustStatus.MODIFIED,
    ]


def test_build_entry_report_reports_deleted_policy_and_still_checks_files(
    policy: Path, script: Path
) -> None:
    entry = _make_entry(policy, script)
    policy.unlink()

    report = build_entry_report(entry)

    assert _get_statuses(report) == [TrustStatus.MISSING, TrustStatus.TRUSTED]
    assert report.entries[0].detail
    assert report.entries[0].trusted_at == TRUSTED_AT


def test_build_entry_report_reports_deleted_file(policy: Path, script: Path) -> None:
    entry = _make_entry(policy, script)
    script.unlink()

    report = build_entry_report(entry)

    assert _get_statuses(report) == [TrustStatus.TRUSTED, TrustStatus.MISSING]
    # The original path is shown, not the normalized key
    assert report.entries[1].path == script
