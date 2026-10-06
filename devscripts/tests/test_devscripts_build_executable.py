import ast
from collections.abc import Iterator
from itertools import chain
from pathlib import Path

import build_executable

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRECTORY = REPO_ROOT / "src" / "powerrules"


def _find_imported_modules(path: Path) -> Iterator[str]:
    """Yield the absolute module names imported by a Python file.

    "from package import name" may import a submodule, so both variants are yielded.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module
            yield from (f"{node.module}.{alias.name}" for alias in node.names)


def test_source_does_not_import_excluded_modules() -> None:
    # The exclusions of all platforms are checked, no platform may depend on an excluded module
    excluded_modules = {
        *build_executable.NOFOLLOW_IMPORT_TO,
        *chain.from_iterable(build_executable.PLATFORM_NOFOLLOW_IMPORT_TO.values()),
    }
    # A module is excluded if it is the excluded module itself or one of its submodules
    excluded_submodule_prefixes = tuple(f"{module}." for module in excluded_modules)

    conflicts = sorted(
        {
            f"{path.relative_to(REPO_ROOT).as_posix()}: {module}"
            for path in SOURCE_DIRECTORY.rglob("*.py")
            for module in _find_imported_modules(path)
            if module in excluded_modules
            or module.startswith(excluded_submodule_prefixes)
        }
    )

    assert not conflicts, (
        "PowerRules imports modules which are excluded from the executable:\n"
        + "\n".join(conflicts)
    )
