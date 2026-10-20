import contextlib
import hashlib
import os
import tempfile
from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from powerrules.engine.exceptions import FileIntegrityError, TrustStoreError

TRUST_STORE_DIRECTORY_NAME = ".powerrules"
TRUST_STORE_FILE_NAME = "trust.json"

# Identifies the hash algorithm, so the digests can be migrated to another algorithm later
_DIGEST_PREFIX = "sha256:"


class TrustStatus(StrEnum):
    """Describe whether a policy or one of its trusted files is trusted."""

    TRUSTED = "trusted"
    # The policy or file was never trusted at this location
    UNKNOWN = "unknown"
    # The policy or file was trusted, but its content is different now
    MODIFIED = "modified"
    # A trusted file does not exist or cannot be read
    MISSING = "missing"


class TrustedFileEntry(BaseModel):
    """A trusted file which a policy depends on."""

    model_config = ConfigDict(frozen=True)

    # Absolute path of the file with all symbolic links resolved, in its original spelling
    path: str
    digest: str


class TrustEntry(BaseModel):
    """A trusted policy."""

    model_config = ConfigDict(frozen=True)

    # Absolute path of the policy with all symbolic links resolved
    path: str
    digest: str
    trusted_at: datetime
    # The "trusted_files" of the policy, the keys are normalized with "make_path_key()"
    trusted_files: dict[str, TrustedFileEntry] = Field(default_factory=dict)


def get_digest_status(trusted_digest: str | None, current_digest: str) -> TrustStatus:
    """Determine the trust status of a policy or a trusted file by comparing digests.

    Args:
        trusted_digest: The digest which was stored when the policy was trusted, or None if it was never trusted.
        current_digest: Digest of the current content.

    Returns:
        Whether the content is trusted, unknown or was modified since it was trusted.
    """
    if trusted_digest is None:
        return TrustStatus.UNKNOWN

    if trusted_digest != current_digest:
        return TrustStatus.MODIFIED

    return TrustStatus.TRUSTED


class _TrustStoreFile(BaseModel):
    """Content of the trust store file."""

    version: Literal[1] = 1
    # The keys are the normalized paths of the policies, see "make_path_key()"
    policies: dict[str, TrustEntry] = Field(default_factory=dict)


def compute_digest(content: bytes) -> str:
    """Compute the digest which identifies the content of a policy or a trusted file.

    Args:
        content: Raw bytes of the policy or the file.

    Returns:
        The SHA-256 digest in the form "sha256:<hex digest>".
    """
    return f"{_DIGEST_PREFIX}{hashlib.sha256(content).hexdigest()}"


def compute_file_digest(path: Path) -> str:
    """Compute the digest of a file, which is read in chunks so large files are not loaded into memory at once.

    Args:
        path: Path of the file.

    Returns:
        The SHA-256 digest in the form "sha256:<hex digest>".

    Raises:
        OSError: If the file cannot be read.
    """
    with path.open("rb") as file:
        return f"{_DIGEST_PREFIX}{hashlib.file_digest(file, 'sha256').hexdigest()}"


def compute_trusted_file_digests(
    base_directory: Path,
    files: Iterable[Path],
) -> dict[Path, str]:
    """Compute the digests of the trusted files of a policy.

    Args:
        base_directory: Directory which relative paths are resolved against (the directory of the policy).
        files: Configured paths of the trusted files.

    Returns:
        The digests keyed by the absolute path of each file with all symbolic links resolved.

    Raises:
        FileIntegrityError: If a file cannot be read.
    """
    digests: dict[Path, str] = {}

    for file in resolve_trusted_files(base_directory, files):
        try:
            digests[file] = compute_file_digest(file)
        except OSError as e:
            raise FileIntegrityError(
                f"Trusted file '{file}' cannot be read: {e}"
            ) from e

    return digests


def make_path_key(path: Path) -> str:
    """Return the key which identifies a policy or a trusted file in the trust store.

    Symbolic links are resolved. Paths are case-insensitive on Windows, "normcase" has no effect on other platforms.

    Args:
        path: Path of the policy or the file.

    Returns:
        The normalized absolute path.
    """
    return os.path.normcase(path.resolve())


def resolve_trusted_files(
    base_directory: Path, files: Iterable[Path]
) -> tuple[Path, ...]:
    """Resolve the configured trusted files and remove duplicates.

    Relative paths are resolved against the base directory and symbolic links are followed.
    Two paths are duplicates if they have the same "make_path_key()".

    This is the single place which defines which files belong to a policy when it is loaded or trusted.
    Right before an action runs, the verifier resolves the files again on purpose, so a link which points to another file than before is detected.

    Args:
        base_directory: Directory which relative paths are resolved against (the directory of the policy).
        files: Configured paths of the trusted files.

    Returns:
        The absolute paths in the order of their first occurrence.
    """
    unique_files: dict[str, Path] = {}

    for file in files:
        resolved_file = (base_directory / file).resolve()
        unique_files.setdefault(make_path_key(resolved_file), resolved_file)

    return tuple(unique_files.values())


class TrustStore:
    """Persist which policies are trusted together with the digest of their content.

    The store is a JSON file in the home directory of the user. It is read and written on every call,
    so changes made by other processes are never missed.
    """

    def __init__(self, path: Path | None = None) -> None:
        """Create a trust store.

        Args:
            path: Path of the trust store file. Defaults to "~/.powerrules/trust.json",
                which is only determined once the store is used.
        """
        self._path = path

    @property
    def path(self) -> Path:
        """Path of the trust store file.

        Raises:
            TrustStoreError: If the home directory of the user cannot be determined.
        """
        if self._path is not None:
            return self._path

        try:
            return Path.home() / TRUST_STORE_DIRECTORY_NAME / TRUST_STORE_FILE_NAME
        except RuntimeError as e:
            raise TrustStoreError(
                "Failed to determine the home directory of the current user"
            ) from e

    def get_entry(self, policy_path: Path) -> TrustEntry | None:
        """Return the trust entry of a policy.

        Args:
            policy_path: Path of the policy file.

        Returns:
            The entry, or None if the policy was never trusted at this location.

        Raises:
            TrustStoreError: If the trust store cannot be read.
        """
        return self._read().policies.get(make_path_key(policy_path))

    def trust(
        self,
        policy_path: Path,
        digest: str,
        trusted_at: datetime,
        trusted_files: Mapping[Path, str] | None = None,
    ) -> None:
        """Trust a policy with the given content. An existing entry of the same policy is replaced.

        Args:
            policy_path: Path of the policy file.
            digest: Digest of the content which is trusted.
            trusted_at: The time when the policy was trusted.
            trusted_files: Digests of the "trusted_files" within a policy,
                keyed by their absolute path with all symbolic links resolved. The keys are normalized with "make_path_key()" when stored.

        Raises:
            TrustStoreError: If the trust store cannot be read or written. A corrupted store is not overwritten.
        """
        store_file = self._read()
        store_file.policies[make_path_key(policy_path)] = TrustEntry(
            # make_path_key() isn't used on purpose to keep the original path
            path=str(policy_path.resolve()),
            digest=digest,
            trusted_at=trusted_at,
            trusted_files={
                make_path_key(file): TrustedFileEntry(
                    # Same as for the policy, the original spelling is kept
                    path=str(file),
                    digest=file_digest,
                )
                for file, file_digest in (trusted_files or {}).items()
            },
        )

        self._write(store_file)

    def untrust(self, policy_path: Path) -> bool:
        """Remove the trust of a policy. The policy file does not have to exist.

        Args:
            policy_path: Path of the policy file.

        Returns:
            True if the policy was trusted before, otherwise False.

        Raises:
            TrustStoreError: If the trust store cannot be read or written.
        """
        store_file = self._read()

        if store_file.policies.pop(make_path_key(policy_path), None) is None:
            return False

        self._write(store_file)

        return True

    def list_entries(self) -> tuple[TrustEntry, ...]:
        """Return all trusted policies sorted by their path.

        Raises:
            TrustStoreError: If the trust store cannot be read.
        """
        return tuple(
            sorted(self._read().policies.values(), key=lambda entry: entry.path)
        )

    def _read(self) -> _TrustStoreFile:
        """Read the trust store. A store which does not exist yet is empty.

        Raises:
            TrustStoreError: If the store cannot be read or is corrupted.
        """
        path = self.path

        try:
            content = path.read_bytes()
        except FileNotFoundError:
            return _TrustStoreFile()
        except OSError as e:
            raise TrustStoreError(f"Failed to read trust store '{path}': {e}") from e

        try:
            return _TrustStoreFile.model_validate_json(content)
        except ValidationError as e:
            raise TrustStoreError(
                f"Trust store '{path}' is corrupted or has an unsupported format, delete it to start over"
            ) from e

    def _write(self, store_file: _TrustStoreFile) -> None:
        """Write the trust store atomically.

        Raises:
            TrustStoreError: If the store cannot be written.
        """
        path = self.path
        temporary_path: Path | None = None

        try:
            # Only the user may access the directory. The mode has no effect on Windows, where the profile of the user is already protected
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            # The temporary file is created next to the store, so it can replace the store atomically (the mode of "mkstemp" is 0600)
            descriptor, temporary_name = tempfile.mkstemp(
                dir=path.parent, prefix=f"{path.name}.", suffix=".tmp"
            )
            temporary_path = Path(temporary_name)

            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write(store_file.model_dump_json(indent=2))

            temporary_path.replace(path)
        except OSError as e:
            if temporary_path is not None:
                with contextlib.suppress(OSError):
                    temporary_path.unlink(missing_ok=True)

            raise TrustStoreError(f"Failed to write trust store '{path}': {e}") from e
