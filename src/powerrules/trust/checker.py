import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from powerrules.engine.exceptions import (
    FileIntegrityError,
    PolicyNotTrustedError,
    TrustStoreError,
)
from powerrules.trust.report import TrustReport, build_trust_report, check_file
from powerrules.trust.store import TrustEntry, TrustStatus, TrustStore, compute_digest

logger = logging.getLogger(__name__)


class PolicyTrustChecker:
    """Check whether a policy and its trusted files are trusted before the policy is used and before its commands run."""

    def __init__(
        self,
        trust_store: TrustStore,
        require_trust_for_actions: bool = False,
        require_trust_for_conditions: bool = False,
        reporter: Callable[[TrustReport], None] | None = None,
        trust_command_builder: Callable[[Path], str] | None = None,
    ) -> None:
        """Create a checker.

        Args:
            trust_store: Store which knows the trusted policies.
            require_trust_for_actions: If True, a policy or file which is not trusted is rejected,
                because the commands of its actions are going to run. Otherwise, the user is only informed.
            require_trust_for_conditions: If True, a policy with a command condition is rejected if it or one of its files
                is not trusted, because the commands of its conditions are going to run (also in a dry run).
                A policy without a command condition is not affected. Otherwise, the user is only informed.
            reporter: Called with the trust report before the result is enforced, e.g. to display it.
                None skips the report. It is only used when a policy is loaded, not when files are verified.
            trust_command_builder: Builds the command which trusts a policy, which is shown in error messages.
                None only mentions "trust add" without the program.
        """
        self.trust_store = trust_store
        self.require_trust_for_actions = require_trust_for_actions
        self.require_trust_for_conditions = require_trust_for_conditions
        self.reporter = reporter
        self.trust_command_builder = trust_command_builder

    def _build_trust_hint(self, policy_path: Path) -> str:
        """Describe how the user can trust the given policy."""
        if self.trust_command_builder is None:
            return "run 'trust add' to trust them"

        return (
            f"run this command to trust them: {self.trust_command_builder(policy_path)}"
        )

    def verify(
        self,
        policy_path: Path,
        content: bytes,
        trusted_files: Sequence[Path] = (),
        has_command_conditions: bool = False,
    ) -> None:
        """Check the trust status of a policy and its trusted files and report it.

        The policy and every file are checked and reported, even if another one is not trusted.
        An unusable trust store is reported as a warning and everything is treated as not trusted.

        Trust is enforced if it is required for actions, or if it is required for conditions
        and the policy contains a command condition. Otherwise, problems are only logged as warnings.

        Args:
            policy_path: Path of the policy file with all symbolic links resolved.
            content: Raw bytes of the policy, which are used for the check and were parsed already.
            trusted_files: Absolute paths of the trusted files of all rules, including disabled ones.
            has_command_conditions: Whether any rule, including disabled ones, contains a command condition.

        Raises:
            PolicyNotTrustedError: If trust is enforced and the policy or a file is not trusted.
            TrustStoreError: If trust is enforced and the trust store cannot be read.
        """
        enforce = self.require_trust_for_actions or (
            self.require_trust_for_conditions and has_command_conditions
        )
        digest = compute_digest(content)
        entry = self._read_entry(policy_path, "policy", enforce)
        report = build_trust_report(policy_path, digest, entry, trusted_files)

        if self.reporter is not None:
            self.reporter(report)

        if report.is_trusted:
            logger.debug(f"Policy '{policy_path}' and its trusted files are trusted")

            return

        message = f"The policy or its trusted files are not trusted, review them and {self._build_trust_hint(policy_path)}"

        if enforce:
            raise PolicyNotTrustedError(message)

        logger.warning(message)

    def verify_files(self, policy_path: Path, files: Sequence[Path]) -> None:
        """Check that the trusted files of an action are unchanged since the policy was trusted.

        This is meant to run right before the command of an action is started, because a file can change while PowerRules is running.
        Without a trust requirement for actions, problems are only logged as warnings.

        Args:
            policy_path: Path of the policy file with all symbolic links resolved.
            files: Absolute paths of the files to check. Symbolic links are resolved on every call,
                so a link which points to another file than before is detected.

        Raises:
            FileIntegrityError: If trust is required for actions and a file cannot be read, is not trusted yet or was modified.
            TrustStoreError: If trust is required for actions and the trust store cannot be read.
        """
        self._verify_files(policy_path, files, self.require_trust_for_actions)

    def verify_condition_files(self, policy_path: Path, files: Sequence[Path]) -> None:
        """Check that the trusted files of a command condition are unchanged since the policy was trusted.

        This is meant to run right before the command of a condition is started, because a file can change while PowerRules is running.
        Without a trust requirement for conditions, problems are only logged as warnings.

        Args:
            policy_path: Path of the policy file with all symbolic links resolved.
            files: Absolute paths of the files to check. Symbolic links are resolved on every call,
                so a link which points to another file than before is detected.

        Raises:
            FileIntegrityError: If trust is required for conditions and a file cannot be read, is not trusted yet or was modified.
            TrustStoreError: If trust is required for conditions and the trust store cannot be read.
        """
        self._verify_files(policy_path, files, self.require_trust_for_conditions)

    def _verify_files(
        self, policy_path: Path, files: Sequence[Path], enforce: bool
    ) -> None:
        """Check that trusted files are unchanged since the policy was trusted.

        Args:
            policy_path: Path of the policy file with all symbolic links resolved.
            files: Absolute paths of the files to check.
            enforce: Whether a problem is an error. Otherwise, problems are only logged as warnings.

        Raises:
            FileIntegrityError: If trust is enforced and a file cannot be read, is not trusted yet or was modified.
            TrustStoreError: If trust is enforced and the trust store cannot be read.
        """
        entry = self._read_entry(policy_path, "files", enforce)
        trusted_files = entry.trusted_files if entry is not None else {}
        problems = [
            file_entry
            for file_entry in (check_file(file, trusted_files) for file in files)
            if file_entry.status is not TrustStatus.TRUSTED
        ]

        if not problems:
            logger.debug(f"Verified {len(files)} trusted file(s)")

            return

        if enforce:
            descriptions = "; ".join(problem.describe() for problem in problems)

            raise FileIntegrityError(
                f"{descriptions}, review them and {self._build_trust_hint(policy_path)}"
            )

        for problem in problems:
            logger.warning(problem.describe())

    def _read_entry(
        self, policy_path: Path, subject: str, enforce: bool
    ) -> TrustEntry | None:
        """Read the trust entry of a policy.

        Args:
            policy_path: Path of the policy file with all symbolic links resolved.
            subject: What is treated as not trusted if the store is unusable, used in the warning.
            enforce: Whether an unusable store is an error. Otherwise, it is only logged as a warning.

        Returns:
            The entry, or None if the policy was never trusted or the store is unusable and trust is not enforced.

        Raises:
            TrustStoreError: If trust is enforced and the trust store cannot be read.
        """
        try:
            return self.trust_store.get_entry(policy_path)
        except TrustStoreError as e:
            if enforce:
                raise

            logger.warning(f"{e}, treating the {subject} as not trusted")

            return None
