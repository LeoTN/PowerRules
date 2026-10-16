from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from powerrules.trust.store import (
    TrustedFileEntry,
    TrustEntry,
    TrustStatus,
    compute_file_digest,
    get_digest_status,
    make_path_key,
)

_STATUS_DESCRIPTIONS = {
    TrustStatus.TRUSTED: "is trusted",
    TrustStatus.UNKNOWN: "is not trusted yet",
    TrustStatus.MODIFIED: "was modified since it was trusted",
    TrustStatus.MISSING: "cannot be read",
}


@dataclass(frozen=True)
class TrustReportEntry:
    """The trust status of the policy or one of its trusted files."""

    path: Path
    status: TrustStatus
    is_policy: bool = False
    # The reason why a file cannot be read, None otherwise
    detail: str | None = None
    # When the policy was trusted, only set for the policy and only if it was trusted before
    trusted_at: datetime | None = None

    def describe(self) -> str:
        """Describe the entry in one sentence, e.g. "File '/scripts/backup.sh' was modified since it was trusted"."""
        subject = "Policy" if self.is_policy else "File"
        description = f"{subject} '{self.path}' {_STATUS_DESCRIPTIONS[self.status]}"

        return f"{description}: {self.detail}" if self.detail else description


@dataclass(frozen=True)
class TrustReport:
    """The trust status of a policy and all of its trusted files. The policy is always the first entry."""

    entries: tuple[TrustReportEntry, ...]

    @property
    def is_trusted(self) -> bool:
        """Whether the policy and all of its trusted files are trusted."""
        return all(entry.status is TrustStatus.TRUSTED for entry in self.entries)


def check_file(
    file: Path, trusted_files: Mapping[str, TrustedFileEntry]
) -> TrustReportEntry:
    """Compare a file with the digest which was stored when the policy was trusted.

    Args:
        file: Path of the file. Symbolic links are resolved.
        trusted_files: Trusted files keyed by "make_path_key()" of the file.

    Returns:
        The trust status of the file.
    """
    resolved_file = file.resolve()

    try:
        current_digest = compute_file_digest(resolved_file)
    except OSError as e:
        return TrustReportEntry(resolved_file, TrustStatus.MISSING, detail=str(e))

    trusted_file = trusted_files.get(make_path_key(resolved_file))
    trusted_digest = trusted_file.digest if trusted_file is not None else None

    return TrustReportEntry(
        resolved_file, get_digest_status(trusted_digest, current_digest)
    )


def build_trust_report(
    policy_path: Path,
    policy_digest: str,
    entry: TrustEntry | None,
    trusted_files: Iterable[Path],
) -> TrustReport:
    """Determine the trust status of a policy and all of its trusted files.

    Every file is checked, no matter whether another one is not trusted.

    Args:
        policy_path: Path of the policy with all symbolic links resolved.
        policy_digest: Digest of the current content of the policy.
        entry: The trust entry of the policy, or None if it was never trusted.
        trusted_files: Absolute paths of the trusted files of all rules, including disabled ones.
            They must already be resolved and free of duplicates, see "resolve_trusted_files()".

    Returns:
        The report with the policy as first entry, followed by each file.
    """
    trusted_files_by_key = entry.trusted_files if entry is not None else {}
    trusted_policy_digest = entry.digest if entry is not None else None

    return TrustReport(
        (
            TrustReportEntry(
                policy_path,
                get_digest_status(trusted_policy_digest, policy_digest),
                is_policy=True,
                trusted_at=entry.trusted_at if entry is not None else None,
            ),
            *(check_file(file, trusted_files_by_key) for file in trusted_files),
        )
    )


def build_entry_report(entry: TrustEntry) -> TrustReport:
    """Determine the current trust status of a policy from the trust store and its trusted files.

    The policy and the files are read again, so the report shows whether they still match the stored digests.

    Args:
        entry: The trust entry of the policy.

    Returns:
        The report with the policy as first entry, followed by each file of the entry.
    """
    policy_path = Path(entry.path)

    try:
        policy_status = get_digest_status(
            entry.digest, compute_file_digest(policy_path)
        )
        policy_detail = None
    except OSError as e:
        policy_status = TrustStatus.MISSING
        policy_detail = str(e)

    return TrustReport(
        (
            TrustReportEntry(
                policy_path,
                policy_status,
                is_policy=True,
                detail=policy_detail,
                trusted_at=entry.trusted_at,
            ),
            *(
                check_file(Path(trusted_file.path), entry.trusted_files)
                for trusted_file in entry.trusted_files.values()
            ),
        )
    )
