from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from powerrules.trust.store import (
    TrustEntry,
    TrustStatus,
    compute_file_digest,
    get_entry_status,
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


def check_file(file: Path, trusted_digests: Mapping[str, str]) -> TrustReportEntry:
    """Compare a file with the digest which was stored when the policy was trusted.

    Args:
        file: Path of the file. Symbolic links are resolved.
        trusted_digests: Trusted digests keyed by "make_path_key()" of the file.

    Returns:
        The trust status of the file.
    """
    resolved_file = file.resolve()

    try:
        current_digest = compute_file_digest(resolved_file)
    except OSError as e:
        return TrustReportEntry(resolved_file, TrustStatus.MISSING, detail=str(e))

    trusted_digest = trusted_digests.get(make_path_key(resolved_file))

    if trusted_digest is None:
        status = TrustStatus.UNKNOWN
    elif trusted_digest != current_digest:
        status = TrustStatus.MODIFIED
    else:
        status = TrustStatus.TRUSTED

    return TrustReportEntry(resolved_file, status)


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

    Returns:
        The report with the policy as first entry, followed by each file once.
    """
    trusted_digests = entry.trusted_files if entry is not None else {}
    entries = [
        TrustReportEntry(
            policy_path, get_entry_status(entry, policy_digest), is_policy=True
        )
    ]

    # A file which is used by several actions is only checked once
    unique_files = {make_path_key(file): file.resolve() for file in trusted_files}

    for file in unique_files.values():
        entries.append(check_file(file, trusted_digests))

    return TrustReport(tuple(entries))
