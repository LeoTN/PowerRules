from pathlib import Path

import pytest

from tests.helpers import BACKUP_SCRIPT_NAME, EMPTY_POLICY_CONTENT, write_resolved_file


@pytest.fixture
def policy(tmp_path: Path) -> Path:
    path = tmp_path / "powerrules.yaml"
    # Write as bytes because Windows could end line with "\r\n" instead of "\n"
    path.write_bytes(EMPTY_POLICY_CONTENT)
    return path.resolve()


@pytest.fixture
def script(tmp_path: Path) -> Path:
    return write_resolved_file(tmp_path / BACKUP_SCRIPT_NAME, "echo backup")
