import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from powerrules.engine.exceptions import FileIntegrityError, TrustStoreError
from powerrules.trust.store import (
    TRUST_STORE_DIRECTORY_NAME,
    TRUST_STORE_FILE_NAME,
    TrustedFileEntry,
    TrustEntry,
    TrustStatus,
    TrustStore,
    compute_digest,
    compute_file_digest,
    compute_trusted_file_digests,
    get_digest_status,
    make_path_key,
    resolve_trusted_files,
)
from tests.helpers import (
    BACKUP_SCRIPT_NAME,
    SCRIPT_DIRECTORY_NAME,
    TRUSTED_AT,
    create_symlink,
    lowercase_normcase,
    write_file,
)

MODULE = "powerrules.trust.store"


##############
# Digest tests
##############


def test_compute_digest_returns_prefixed_sha256() -> None:
    assert compute_digest(b"test") == f"sha256:{hashlib.sha256(b'test').hexdigest()}"


def test_compute_digest_differs_for_different_content() -> None:
    assert compute_digest(b"first") != compute_digest(b"second")


def test_compute_file_digest_matches_digest_of_content(tmp_path: Path) -> None:
    # Larger than the chunk size of "hashlib.file_digest"
    content = b"powerrules" * 200_000
    file = tmp_path / "file.bin"
    file.write_bytes(content)

    assert compute_file_digest(file) == compute_digest(content)


def test_compute_file_digest_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compute_file_digest(tmp_path / "missing.txt")


@pytest.mark.parametrize(
    ("trusted_digest", "current_digest", "expected"),
    [
        (None, "sha256:a", TrustStatus.UNKNOWN),
        ("sha256:a", "sha256:a", TrustStatus.TRUSTED),
        ("sha256:a", "sha256:b", TrustStatus.MODIFIED),
    ],
)
def test_get_digest_status_compares_digests(
    trusted_digest: str | None,
    current_digest: str,
    expected: TrustStatus,
) -> None:
    assert get_digest_status(trusted_digest, current_digest) is expected


################
# Path key tests
################


def test_make_path_key_resolves_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert make_path_key(Path("file.txt")) == os.path.normcase(
        tmp_path.resolve() / "file.txt"
    )


def test_make_path_key_resolves_symbolic_links(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    write_file(target)
    link = tmp_path / "link.txt"
    create_symlink(link, target)

    assert make_path_key(link) == make_path_key(target)


def test_make_path_key_ignores_case_where_paths_are_case_insensitive(
    tmp_path: Path,
) -> None:
    with patch(f"{MODULE}.os.path.normcase", lowercase_normcase):
        assert make_path_key(tmp_path / "File.TXT") == make_path_key(
            tmp_path / "file.txt"
        )


#############################
# resolve_trusted_files tests
#############################


def test_resolve_trusted_files_resolves_relative_paths_against_base_directory(
    tmp_path: Path,
) -> None:
    assert resolve_trusted_files(tmp_path, [Path("scripts/a.sh")]) == (
        tmp_path.resolve() / SCRIPT_DIRECTORY_NAME / "a.sh",
    )


def test_resolve_trusted_files_keeps_absolute_paths(tmp_path: Path) -> None:
    other = (tmp_path / "other" / "b.sh").resolve()

    assert resolve_trusted_files(tmp_path / "base", [other]) == (other,)


def test_resolve_trusted_files_removes_duplicates_and_keeps_order(
    tmp_path: Path,
) -> None:
    (tmp_path / "sub").mkdir()

    result = resolve_trusted_files(
        tmp_path,
        [
            Path("b.sh"),
            Path("a.sh"),
            Path("./b.sh"),
            Path("sub") / ".." / "a.sh",
        ],
    )

    assert result == (tmp_path.resolve() / "b.sh", tmp_path.resolve() / "a.sh")


def test_resolve_trusted_files_treats_symbolic_link_and_target_as_duplicates(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.sh"
    write_file(target)
    create_symlink(tmp_path / "link.sh", target)

    assert resolve_trusted_files(tmp_path, [Path("link.sh"), Path("target.sh")]) == (
        target.resolve(),
    )


def test_resolve_trusted_files_removes_duplicates_which_differ_in_case_only(
    tmp_path: Path,
) -> None:
    with patch(f"{MODULE}.os.path.normcase", lowercase_normcase):
        result = resolve_trusted_files(tmp_path, [Path("Backup.sh"), Path("backup.SH")])

    # The first spelling is kept
    assert result == (tmp_path.resolve() / "Backup.sh",)


def test_resolve_trusted_files_returns_empty_tuple_without_files(
    tmp_path: Path,
) -> None:
    assert resolve_trusted_files(tmp_path, []) == ()


####################################
# compute_trusted_file_digests tests
####################################


def test_compute_trusted_file_digests_returns_digests_by_resolved_path(
    tmp_path: Path,
) -> None:
    (tmp_path / SCRIPT_DIRECTORY_NAME).mkdir()
    first = tmp_path / SCRIPT_DIRECTORY_NAME / "a.sh"
    second = tmp_path / "b.sh"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    digests = compute_trusted_file_digests(
        tmp_path, [Path("scripts/a.sh"), Path("b.sh")]
    )

    assert digests == {
        first.resolve(): compute_digest(b"first"),
        second.resolve(): compute_digest(b"second"),
    }


def test_compute_trusted_file_digests_uses_each_file_once(tmp_path: Path) -> None:
    (tmp_path / "a.sh").write_text("content", encoding="utf-8")

    digests = compute_trusted_file_digests(tmp_path, [Path("a.sh"), Path("./a.sh")])

    assert list(digests) == [(tmp_path / "a.sh").resolve()]


def test_compute_trusted_file_digests_returns_empty_dict_without_files(
    tmp_path: Path,
) -> None:
    assert compute_trusted_file_digests(tmp_path, []) == {}


@pytest.mark.parametrize("is_directory", [False, True])
def test_compute_trusted_file_digests_rejects_unreadable_file(
    tmp_path: Path,
    is_directory: bool,
) -> None:
    if is_directory:
        (tmp_path / "unreadable").mkdir()

    with pytest.raises(FileIntegrityError, match="cannot be read"):
        compute_trusted_file_digests(tmp_path, [Path("unreadable")])


##################
# TrustStore tests
##################


def test_trust_store_returns_none_for_unknown_policy(
    trust_store: TrustStore, tmp_path: Path
) -> None:
    assert trust_store.get_entry(tmp_path / "powerrules.yaml") is None


def test_trust_store_returns_saved_entry(
    trust_store: TrustStore, tmp_path: Path
) -> None:
    policy = (tmp_path / "powerrules.yaml").resolve()
    script = (tmp_path / SCRIPT_DIRECTORY_NAME / BACKUP_SCRIPT_NAME).resolve()

    trust_store.trust(policy, "sha256:policy", TRUSTED_AT, {script: "sha256:script"})

    assert trust_store.get_entry(policy) == TrustEntry(
        path=str(policy),
        digest="sha256:policy",
        trusted_at=TRUSTED_AT,
        trusted_files={
            make_path_key(script): TrustedFileEntry(
                path=str(script), digest="sha256:script"
            )
        },
    )


def test_trust_store_saves_entry_without_trusted_files(
    trust_store: TrustStore, tmp_path: Path
) -> None:
    policy = tmp_path / "powerrules.yaml"

    trust_store.trust(policy, "sha256:policy", TRUSTED_AT)

    entry = trust_store.get_entry(policy)

    assert entry is not None
    assert entry.trusted_files == {}


def test_trust_store_keeps_original_spelling_of_trusted_files(
    trust_store: TrustStore, tmp_path: Path
) -> None:
    policy = (tmp_path / "powerrules.yaml").resolve()
    script = (tmp_path / "Scripts" / "Backup.SH").resolve()

    with patch(f"{MODULE}.os.path.normcase", lowercase_normcase):
        trust_store.trust(
            policy, "sha256:policy", TRUSTED_AT, {script: "sha256:script"}
        )
        entry = trust_store.get_entry(policy)

    assert entry is not None
    # The key is normalized, the path is shown to the user and stays as it is
    assert list(entry.trusted_files) == [str(script).lower()]
    assert entry.trusted_files[str(script).lower()].path == str(script)


def test_trust_store_replaces_existing_entry_of_same_policy(
    trust_store: TrustStore, tmp_path: Path
) -> None:
    policy = tmp_path / "powerrules.yaml"
    script = (tmp_path / BACKUP_SCRIPT_NAME).resolve()

    trust_store.trust(policy, "sha256:old", TRUSTED_AT, {script: "sha256:old-script"})
    trust_store.trust(policy, "sha256:new", TRUSTED_AT)

    entry = trust_store.get_entry(policy)

    assert entry is not None
    assert entry.digest == "sha256:new"
    # The files of the old entry are gone
    assert entry.trusted_files == {}
    assert len(trust_store.list_entries()) == 1


def test_trust_store_keeps_other_policies_when_trusting(
    trust_store: TrustStore, tmp_path: Path
) -> None:
    trust_store.trust(tmp_path / "first.yaml", "sha256:first", TRUSTED_AT)
    trust_store.trust(tmp_path / "second.yaml", "sha256:second", TRUSTED_AT)

    assert [entry.digest for entry in trust_store.list_entries()] == [
        "sha256:first",
        "sha256:second",
    ]


def test_trust_store_finds_entry_with_another_spelling_of_the_path(
    trust_store: TrustStore, tmp_path: Path
) -> None:
    (tmp_path / "other").mkdir()
    trust_store.trust(tmp_path / "powerrules.yaml", "sha256:policy", TRUSTED_AT)

    assert (
        trust_store.get_entry(tmp_path / "other" / ".." / "powerrules.yaml") is not None
    )


def test_trust_store_persists_entries_between_instances(
    trust_store: TrustStore, trust_store_path: Path, tmp_path: Path
) -> None:
    policy = tmp_path / "powerrules.yaml"
    trust_store.trust(policy, "sha256:policy", TRUSTED_AT)

    assert TrustStore(trust_store_path).get_entry(policy) is not None


def test_trust_store_writes_documented_file_format(
    trust_store: TrustStore, trust_store_path: Path, tmp_path: Path
) -> None:
    policy = (tmp_path / "powerrules.yaml").resolve()
    script = (tmp_path / BACKUP_SCRIPT_NAME).resolve()

    trust_store.trust(policy, "sha256:policy", TRUSTED_AT, {script: "sha256:script"})

    data = json.loads(trust_store_path.read_text(encoding="utf-8"))
    policy_data = data["policies"][make_path_key(policy)]

    assert data["version"] == 1
    assert policy_data["path"] == str(policy)
    assert policy_data["digest"] == "sha256:policy"
    assert policy_data["trusted_files"][make_path_key(script)] == {
        "path": str(script),
        "digest": "sha256:script",
    }


def test_trust_store_creates_missing_directories(
    trust_store: TrustStore, trust_store_path: Path, tmp_path: Path
) -> None:
    assert not trust_store_path.parent.exists()

    trust_store.trust(tmp_path / "powerrules.yaml", "sha256:policy", TRUSTED_AT)

    assert trust_store_path.is_file()


def test_trust_store_leaves_no_temporary_files(
    trust_store: TrustStore, trust_store_path: Path, tmp_path: Path
) -> None:
    trust_store.trust(tmp_path / "first.yaml", "sha256:first", TRUSTED_AT)
    trust_store.trust(tmp_path / "second.yaml", "sha256:second", TRUSTED_AT)

    assert list(trust_store_path.parent.iterdir()) == [trust_store_path]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_trust_store_file_is_only_accessible_by_the_user(
    trust_store: TrustStore, trust_store_path: Path, tmp_path: Path
) -> None:
    trust_store.trust(tmp_path / "powerrules.yaml", "sha256:policy", TRUSTED_AT)

    assert stat.S_IMODE(trust_store_path.stat().st_mode) == 0o600


###############
# untrust tests
###############


def test_trust_store_untrust_removes_entry(
    trust_store: TrustStore, tmp_path: Path
) -> None:
    policy = tmp_path / "powerrules.yaml"
    other = tmp_path / "other.yaml"
    trust_store.trust(policy, "sha256:policy", TRUSTED_AT)
    trust_store.trust(other, "sha256:other", TRUSTED_AT)

    assert trust_store.untrust(policy) is True
    assert trust_store.get_entry(policy) is None
    assert trust_store.get_entry(other) is not None


def test_trust_store_untrust_returns_false_for_unknown_policy(
    trust_store: TrustStore, trust_store_path: Path, tmp_path: Path
) -> None:
    assert trust_store.untrust(tmp_path / "powerrules.yaml") is False
    # Nothing was written
    assert not trust_store_path.exists()


def test_trust_store_untrust_works_for_deleted_policy(
    trust_store: TrustStore, tmp_path: Path
) -> None:
    policy = tmp_path / "powerrules.yaml"
    policy.write_text("rules: []", encoding="utf-8")
    trust_store.trust(policy, "sha256:policy", TRUSTED_AT)
    policy.unlink()

    assert trust_store.untrust(policy) is True


####################
# list_entries tests
####################


def test_trust_store_lists_no_entries_for_missing_store(
    trust_store: TrustStore,
) -> None:
    assert trust_store.list_entries() == ()


def test_trust_store_lists_entries_sorted_by_path(
    trust_store: TrustStore, tmp_path: Path
) -> None:
    for name in ("c.yaml", "a.yaml", "b.yaml"):
        trust_store.trust(tmp_path / name, f"sha256:{name}", TRUSTED_AT)

    assert [Path(entry.path).name for entry in trust_store.list_entries()] == [
        "a.yaml",
        "b.yaml",
        "c.yaml",
    ]


###########################
# Store location and errors
###########################


def test_trust_store_uses_directory_in_home_by_default(isolated_home: Path) -> None:
    assert (
        TrustStore().path
        == isolated_home / TRUST_STORE_DIRECTORY_NAME / TRUST_STORE_FILE_NAME
    )


def test_trust_store_reports_unknown_home_directory_when_it_is_used() -> None:
    with patch.object(Path, "home", side_effect=RuntimeError("Test failure")):
        # Creating the store must not fail, only using it
        store = TrustStore()

        with pytest.raises(TrustStoreError, match="home directory"):
            store.list_entries()


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"version": 2}',
        '{"version": 1, "policies": {"key": {"path": "policy.yaml"}}}',
    ],
    ids=["no-json", "unknown-version", "incomplete-entry"],
)
def test_trust_store_rejects_corrupted_store(
    trust_store: TrustStore,
    trust_store_path: Path,
    content: str,
) -> None:
    trust_store_path.parent.mkdir(parents=True)
    trust_store_path.write_text(content, encoding="utf-8")

    with pytest.raises(TrustStoreError, match="corrupted or has an unsupported format"):
        trust_store.get_entry(Path("policy.yaml"))


def test_trust_store_does_not_overwrite_corrupted_store(
    trust_store: TrustStore, trust_store_path: Path
) -> None:
    trust_store_path.parent.mkdir(parents=True)
    trust_store_path.write_text("not json", encoding="utf-8")

    with pytest.raises(TrustStoreError):
        trust_store.trust(Path("policy.yaml"), "sha256:policy", TRUSTED_AT)

    assert trust_store_path.read_text(encoding="utf-8") == "not json"


def test_trust_store_reports_unreadable_store(
    trust_store: TrustStore, trust_store_path: Path
) -> None:
    # A directory cannot be read as a file
    trust_store_path.mkdir(parents=True)

    with pytest.raises(TrustStoreError, match="Failed to read trust store"):
        trust_store.list_entries()


def test_trust_store_keeps_old_content_and_cleans_up_when_writing_fails(
    trust_store: TrustStore, trust_store_path: Path, tmp_path: Path
) -> None:
    trust_store.trust(tmp_path / "first.yaml", "sha256:first", TRUSTED_AT)
    content_before = trust_store_path.read_bytes()

    with (
        patch.object(Path, "replace", side_effect=OSError("Test failure")),
        pytest.raises(TrustStoreError, match="Failed to write trust store"),
    ):
        trust_store.trust(tmp_path / "second.yaml", "sha256:second", TRUSTED_AT)

    assert trust_store_path.read_bytes() == content_before
    assert list(trust_store_path.parent.glob("*.tmp")) == []


def test_trust_store_reports_directory_which_cannot_be_created(
    trust_store: TrustStore,
) -> None:
    with (
        patch.object(Path, "mkdir", side_effect=OSError("Test failure")),
        pytest.raises(TrustStoreError, match="Failed to write trust store"),
    ):
        trust_store.trust(Path("policy.yaml"), "sha256:policy", TRUSTED_AT)
