from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from powerrules.application.trust import trust_policy
from powerrules.engine.exceptions import FileIntegrityError
from powerrules.trust.store import (
    TrustedFileEntry,
    TrustStore,
    compute_digest,
    compute_file_digest,
)
from tests.factories import make_clock_provider
from tests.helpers import TRUSTED_AT, create_symlink, make_policy_yaml, write_policy

POLICY_WITH_TRUSTED_FILES = """
rules:
  - name: "Test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - name: "Backup"
        run: "backup"
        trusted_files:
          - scripts/backup.sh
      - name: "Other"
        run: "other"
        trusted_files:
          - scripts/./backup.sh
"""


def test_trust_policy_trusts_policy_and_files(
    trust_store: TrustStore, workspace: Path
) -> None:
    policy = write_policy(workspace, POLICY_WITH_TRUSTED_FILES)
    script = workspace / "scripts" / "backup.sh"

    report = trust_policy(policy, trust_store, make_clock_provider(TRUSTED_AT))

    entry = trust_store.get_entry(policy)

    assert entry is not None
    assert entry.digest == compute_digest(policy.read_bytes())
    assert entry.trusted_at == TRUSTED_AT
    # The file is used by two actions, but only trusted once
    assert list(entry.trusted_files.values()) == [
        TrustedFileEntry(path=str(script), digest=compute_file_digest(script))
    ]
    assert report.is_trusted is True
    assert [entry.path for entry in report.entries] == [policy, script]


def test_trust_policy_without_trusted_files(
    trust_store: TrustStore, workspace: Path
) -> None:
    policy = write_policy(workspace, make_policy_yaml())

    report = trust_policy(policy, trust_store, make_clock_provider(TRUSTED_AT))

    assert [entry.path for entry in report.entries] == [policy]
    assert report.is_trusted is True


def test_trust_policy_trusts_the_modified_content_again(
    trust_store: TrustStore, workspace: Path
) -> None:
    policy = write_policy(workspace, POLICY_WITH_TRUSTED_FILES)
    script = workspace / "scripts" / "backup.sh"
    trust_policy(policy, trust_store, make_clock_provider(TRUSTED_AT))
    script.write_text("echo changed", encoding="utf-8")

    report = trust_policy(policy, trust_store, make_clock_provider(TRUSTED_AT))

    entry = trust_store.get_entry(policy)

    assert entry is not None
    assert entry.trusted_files[next(iter(entry.trusted_files))].digest == (
        compute_file_digest(script)
    )
    assert report.is_trusted is True


def test_trust_policy_resolves_files_against_directory_of_policy(
    trust_store: TrustStore,
    workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = write_policy(workspace, POLICY_WITH_TRUSTED_FILES)
    monkeypatch.chdir(tmp_path)

    report = trust_policy(policy, trust_store, make_clock_provider(TRUSTED_AT))

    assert report.is_trusted is True


def test_trust_policy_accepts_relative_policy_path(
    trust_store: TrustStore, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_policy(workspace, POLICY_WITH_TRUSTED_FILES)
    monkeypatch.chdir(workspace)

    trust_policy(Path("powerrules.yaml"), trust_store, make_clock_provider(TRUSTED_AT))

    assert trust_store.get_entry(workspace / "powerrules.yaml") is not None


def test_trust_policy_stores_symbolic_link_under_the_real_path(
    trust_store: TrustStore, workspace: Path, tmp_path: Path
) -> None:
    policy = write_policy(workspace, POLICY_WITH_TRUSTED_FILES)
    link = tmp_path / "link.yaml"

    create_symlink(link, policy)

    report = trust_policy(link, trust_store, make_clock_provider(TRUSTED_AT))

    assert trust_store.get_entry(policy) is not None
    # The files are resolved against the directory of the real policy
    assert report.is_trusted is True


def test_trust_policy_rejects_invalid_policy(
    trust_store: TrustStore, workspace: Path
) -> None:
    policy = write_policy(workspace, 'rules:\n  - name: "Invalid"\n')

    with pytest.raises(ValidationError):
        trust_policy(policy, trust_store, make_clock_provider(TRUSTED_AT))

    assert trust_store.get_entry(policy) is None


def test_trust_policy_rejects_invalid_yaml(
    trust_store: TrustStore, workspace: Path
) -> None:
    policy = write_policy(workspace, 'rules:\n  - name: "Broken\n')

    with pytest.raises(yaml.YAMLError):
        trust_policy(policy, trust_store, make_clock_provider(TRUSTED_AT))

    assert trust_store.get_entry(policy) is None


def test_trust_policy_rejects_missing_policy(
    trust_store: TrustStore, tmp_path: Path
) -> None:
    with pytest.raises(FileNotFoundError):
        trust_policy(
            tmp_path / "missing.yaml", trust_store, make_clock_provider(TRUSTED_AT)
        )


def test_trust_policy_rejects_missing_trusted_file_without_saving_anything(
    trust_store: TrustStore, workspace: Path
) -> None:
    (workspace / "scripts" / "backup.sh").unlink()
    policy = write_policy(workspace, POLICY_WITH_TRUSTED_FILES)

    with pytest.raises(FileIntegrityError, match="cannot be read"):
        trust_policy(policy, trust_store, make_clock_provider(TRUSTED_AT))

    assert trust_store.get_entry(policy) is None
