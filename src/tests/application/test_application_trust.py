from datetime import datetime
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
from tests.mocks import make_clock_provider

NOW = datetime(2026, 10, 17, 14, 3)

POLICY = """
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

POLICY_WITHOUT_FILES = """
rules:
  - name: "Test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - run: "echo test"
"""


@pytest.fixture
def store(tmp_path: Path) -> TrustStore:
    return TrustStore(tmp_path / "store" / "trust.json")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    directory = tmp_path / "workspace"
    (directory / "scripts").mkdir(parents=True)
    (directory / "scripts" / "backup.sh").write_text("echo backup", encoding="utf-8")
    (directory / "powerrules.yaml").write_text(POLICY, encoding="utf-8")

    return directory.resolve()


def test_trust_policy_trusts_policy_and_files(
    store: TrustStore, workspace: Path
) -> None:
    policy = workspace / "powerrules.yaml"
    script = workspace / "scripts" / "backup.sh"

    report = trust_policy(policy, store, make_clock_provider(NOW))

    entry = store.get_entry(policy)

    assert entry is not None
    assert entry.digest == compute_digest(policy.read_bytes())
    assert entry.trusted_at == NOW
    # The file is used by two actions, but only trusted once
    assert list(entry.trusted_files.values()) == [
        TrustedFileEntry(path=str(script), digest=compute_file_digest(script))
    ]
    assert report.is_trusted is True
    assert [e.path for e in report.entries] == [policy, script]


def test_trust_policy_without_trusted_files(store: TrustStore, workspace: Path) -> None:
    policy = workspace / "powerrules.yaml"
    policy.write_text(POLICY_WITHOUT_FILES, encoding="utf-8")

    report = trust_policy(policy, store, make_clock_provider(NOW))

    assert [e.path for e in report.entries] == [policy]
    assert report.is_trusted is True


def test_trust_policy_trusts_the_modified_content_again(
    store: TrustStore, workspace: Path
) -> None:
    policy = workspace / "powerrules.yaml"
    script = workspace / "scripts" / "backup.sh"
    trust_policy(policy, store, make_clock_provider(NOW))
    script.write_text("echo changed", encoding="utf-8")

    report = trust_policy(policy, store, make_clock_provider(NOW))

    entry = store.get_entry(policy)

    assert entry is not None
    assert entry.trusted_files[next(iter(entry.trusted_files))].digest == (
        compute_file_digest(script)
    )
    assert report.is_trusted is True


def test_trust_policy_resolves_files_against_directory_of_policy(
    store: TrustStore,
    workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    report = trust_policy(
        workspace / "powerrules.yaml", store, make_clock_provider(NOW)
    )

    assert report.is_trusted is True


def test_trust_policy_accepts_relative_policy_path(
    store: TrustStore, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(workspace)

    trust_policy(Path("powerrules.yaml"), store, make_clock_provider(NOW))

    assert store.get_entry(workspace / "powerrules.yaml") is not None


def test_trust_policy_stores_symbolic_link_under_the_real_path(
    store: TrustStore, workspace: Path, tmp_path: Path
) -> None:
    link = tmp_path / "link.yaml"

    try:
        link.symlink_to(workspace / "powerrules.yaml")
    except (OSError, NotImplementedError):
        pytest.skip("Symbolic links are not available")

    report = trust_policy(link, store, make_clock_provider(NOW))

    assert store.get_entry(workspace / "powerrules.yaml") is not None
    # The files are resolved against the directory of the real policy
    assert report.is_trusted is True


def test_trust_policy_rejects_invalid_policy(
    store: TrustStore, workspace: Path
) -> None:
    policy = workspace / "powerrules.yaml"
    policy.write_text('rules:\n  - name: "Invalid"\n', encoding="utf-8")

    with pytest.raises(ValidationError):
        trust_policy(policy, store, make_clock_provider(NOW))

    assert store.get_entry(policy) is None


def test_trust_policy_rejects_invalid_yaml(store: TrustStore, workspace: Path) -> None:
    policy = workspace / "powerrules.yaml"
    policy.write_text('rules:\n  - name: "Broken\n', encoding="utf-8")

    with pytest.raises(yaml.YAMLError):
        trust_policy(policy, store, make_clock_provider(NOW))

    assert store.get_entry(policy) is None


def test_trust_policy_rejects_missing_policy(store: TrustStore, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        trust_policy(tmp_path / "missing.yaml", store, make_clock_provider(NOW))


def test_trust_policy_rejects_missing_trusted_file_without_saving_anything(
    store: TrustStore, workspace: Path
) -> None:
    (workspace / "scripts" / "backup.sh").unlink()
    policy = workspace / "powerrules.yaml"

    with pytest.raises(FileIntegrityError, match="cannot be read"):
        trust_policy(policy, store, make_clock_provider(NOW))

    assert store.get_entry(policy) is None
