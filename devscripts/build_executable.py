"""Build a standalone PowerRules executable for the current platform using Nuitka.

Usage:
    poetry run python devscripts/build_executable.py [--output-dir DIR] [--expected-version VERSION]
"""

import argparse
import importlib
import pkgutil
import platform
import re
import subprocess
import sys
import unicodedata
from collections.abc import Collection
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from tests.smoke_test_executable import run_smoke_tests

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRY_POINT = REPO_ROOT / "src" / "powerrules"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "dist" / "executable"
ICON_DIRECTORY = REPO_ROOT / "assets" / "icon"
# Maps the OS name to the Nuitka icon option and the icon file name.
# macOS is missing on purpose: a bare single-file binary cannot carry an icon there
PLATFORM_ICONS: dict[str, tuple[str, str]] = {
    "windows": ("--windows-icon-from-ico", "executable_icon.ico"),
    "linux": ("--linux-icon", "executable_icon.png"),
}
VERSION_PATTERN = re.compile(r"(?P<base>\d+\.\d+\.\d+)(?:b(?P<beta>\d+))?")

#########################################################
# Reduce the binary size by excluding unnecessary modules
#########################################################

RICH_UNICODE_DATA_PACKAGE = "rich._unicode_data"
RICH_UNICODE_TABLE_PREFIX = "unicode"


def get_submodules_to_exclude(
    package_name: str,
    kept_modules: Collection[str],
    name_prefix: str = "",
) -> tuple[str, ...]:
    """Return all submodules of a package except the explicitly kept modules.

    Nuitka's "--nofollow-import-to" overrides "--include-module", so a package cannot be excluded as a whole while some of its modules are kept.
    Every submodule which is not needed is excluded individually instead.

    Args:
        package_name: Fully qualified name of the package (e.g. "pygments.lexers").
        kept_modules: Fully qualified names of the submodules which have to stay available.
        name_prefix: Only submodules whose own name starts with this prefix are considered. Defaults to all.

    Returns:
        The sorted, fully qualified names of all submodules to exclude.
    """
    package = importlib.import_module(package_name)
    package_prefix = f"{package_name}."

    modules = {
        module_info.name
        for module_info in pkgutil.walk_packages(
            package.__path__,
            prefix=package_prefix,
        )
        if module_info.name.removeprefix(package_prefix).startswith(name_prefix)
    }

    return tuple(sorted(modules - set(kept_modules)))


def get_rich_unicode_modules_to_keep() -> frozenset[str]:
    """Return the Unicode width tables of rich which may be loaded at runtime.

    Rich loads exactly one table by name, chosen by the Unicode version of the Python interpreter,
    and falls back to the newest table at or below that version.
    Python is bundled into the executable, so the version of the build interpreter is the version used at runtime.
    The newest table is kept as an additional safety net.

    Returns:
        The fully qualified names of the Unicode tables to keep.
    """
    package_prefix = f"{RICH_UNICODE_DATA_PACKAGE}."
    table_prefix = f"{package_prefix}{RICH_UNICODE_TABLE_PREFIX}"
    package = importlib.import_module(RICH_UNICODE_DATA_PACKAGE)

    table_modules = {
        module_info.name
        for module_info in pkgutil.iter_modules(package.__path__, prefix=package_prefix)
        if module_info.name.startswith(table_prefix)
    }

    def get_table_version(module_name: str) -> tuple[int, ...]:
        # "rich._unicode_data.unicode15-1-0" -> (15, 1, 0)
        return tuple(
            int(part) for part in module_name.removeprefix(table_prefix).split("-")
        )

    interpreter_version = tuple(
        int(part) for part in unicodedata.unidata_version.split(".")
    )
    newest_table = max(table_modules, key=get_table_version)
    compatible_tables = [
        module_name
        for module_name in table_modules
        if get_table_version(module_name) <= interpreter_version
    ]
    closest_table = max(compatible_tables, key=get_table_version, default=newest_table)

    return frozenset({closest_table, newest_table})


# Modules which are loaded by name at runtime, so they have to be included explicitly
# (the rest of their packages is excluded by get_submodules_to_exclude)
KEPT_MODULES = frozenset(
    {
        # Lexers which have to stay available for pygments and rich tracebacks
        "pygments.lexers._mapping",
        "pygments.lexers.python",
        "pygments.lexers.special",
        # Styles are only needed for pygments themes. Rich tracebacks use rich's own ANSI theme by default,
        # "monokai" is the default theme name of rich.syntax and serves as a safety net together with "default"
        "pygments.styles._mapping",
        "pygments.styles.default",
        "pygments.styles.monokai",
        # The Unicode width table matching the bundled Python (and the newest one)
        *get_rich_unicode_modules_to_keep(),
    }
)

STATIC_NOFOLLOW_IMPORT_TO = (
    # Only reachable through logging.handlers (SMTPHandler/HTTPHandler). Removes libssl-3.dll and libcrypto-3.dll,
    # hashlib falls back to its built-in implementations
    "ssl",
    "_ssl",
    "_hashlib",
    "smtplib",
    "http.client",
    "ftplib",
    "imaplib",
    "poplib",
    # Interactive help and REPL, never used by a CLI tool
    "pydoc",
    "pydoc_data",
    "_pyrepl",
    "code",
    "codeop",
    "rlcompleter",
    "http.server",
    # The pure Python YAML loader is used, not the libyaml extension
    "yaml.cyaml",
    "yaml._yaml",
    # Only imported by the mypy plugin of pydantic
    "pydantic.mypy",
    # Pydantic compatibility modules currently not used by PowerRules
    # (excluding the whole package also removes its __init__, which "pydantic.v1.*" did not)
    "pydantic.v1",
    "pydantic.class_validators",
    "pydantic.datetime_parse",
    # Deprecated Pydantic V1 style methods of BaseModel (.json(), .parse_obj(), .copy(), ...) import this lazily
    "pydantic.deprecated",
    "pydantic.env_settings",
    "pydantic.error_wrappers",
    "pydantic.json",
    "pydantic.parse",
    "pydantic.schema",
    "pydantic.typing",
    "pydantic.utils",
    "pydantic.validators",
    # Only imported by pydantic.deprecated, PowerRules does not use network or color types
    "pydantic.color",
    "pydantic.networks",
    # The standard library is bundled as a whole by Nuitka, these modules are not imported by anything
    "__hello__",
    "__phello__",
    "_markupbase",
    "cmd",
    "filecmp",
    "fileinput",
    "graphlib",
    "html.parser",
    "importlib.metadata.diagnose",
    "mimetypes",
    "modulefinder",
    "netrc",
    "nturl2path",
    "pickletools",
    "pkgutil",
    "pprint",
    "pstats",
    "pyclbr",
    "sched",
    "socketserver",
    "sre_compile",
    "sre_constants",
    "sre_parse",
    "symtable",
    "timeit",
    "tomllib",
    "trace",
    # Pure Python fallbacks of modules which are always available as built-in or extension modules
    "_py_abc",
    "_pyio",
    "_pydecimal",
    # Platform support of the standard library for platforms PowerRules does not run on
    "_aix_support",
    "_android_support",
    "_apple_support",
    # Compression is only imported lazily or guarded by try/except ImportError (shutil, zipfile, tarfile).
    # Removes _bz2.pyd and _lzma.pyd
    "bz2",
    "_bz2",
    "lzma",
    "_lzma",
    "gzip",
    "_compression",
    "tarfile",
    # Only imported lazily by functions PowerRules never calls
    # (command line entry points of dis, py_compile, random, uuid and webbrowser)
    "argparse",
    # zipfile.PyZipFile
    "py_compile",
    # random (only used by a self test function)
    "statistics",
    # typer.launch()
    "webbrowser",
    # Only imported lazily by rich features PowerRules does not use (inspect, print_json, status spinners, ANSI decoding)
    "rich._inspect",
    "rich.json",
    "rich.status",
    "rich.spinner",
    "rich._spinners",
    "rich.live",
    "rich.live_render",
    "rich.file_proxy",
    "rich.ansi",
)
# Modules which are pulled in by dependencies or the standard library, but are never used by PowerRules at runtime
NOFOLLOW_IMPORT_TO = (
    *STATIC_NOFOLLOW_IMPORT_TO,
    # Lexers are only needed to highlight source code in rich tracebacks
    *get_submodules_to_exclude("pygments.lexers", KEPT_MODULES),
    # Pygments themes are loaded by name and are not used by the default rich traceback theme
    *get_submodules_to_exclude("pygments.styles", KEPT_MODULES),
    # Rich only loads the Unicode width table of the bundled Python version
    *get_submodules_to_exclude(
        RICH_UNICODE_DATA_PACKAGE,
        KEPT_MODULES,
        name_prefix=RICH_UNICODE_TABLE_PREFIX,
    ),
)
WINDOWS_NOFOLLOW_IMPORT_TO = (
    # GUI parts of pywin32 and XML support, which is only imported by the BSD backend of psutil
    "pywin",
    "win32ui",
    "xml",
    # Platform-specific psutil backends not used by the Windows build
    "psutil._psaix",
    "psutil._psbsd",
    "psutil._pslinux",
    "psutil._psosx",
    "psutil._pssunos",
    # Windows Event Log support from logging.handlers, not used by PowerRules
    "win32evtlogutil",
    # macOS specific part of the standard library (sysconfig)
    "_osx_support",
)
LINUX_NOFOLLOW_IMPORT_TO = (
    # Platform-specific psutil backends not used by the Linux build
    "psutil._psaix",
    "psutil._psbsd",
    "psutil._psosx",
    "psutil._pssunos",
    "psutil._pswindows",
    # macOS specific part of the standard library (sysconfig)
    "_osx_support",
)
MACOS_NOFOLLOW_IMPORT_TO = (
    # Platform-specific psutil backends not used by the macOS build
    "psutil._psaix",
    "psutil._psbsd",
    "psutil._pslinux",
    "psutil._pssunos",
    "psutil._pswindows",
)
# Maps the normalized OS name (see get_os_name) to its platform-specific exclusions
PLATFORM_NOFOLLOW_IMPORT_TO = {
    "windows": WINDOWS_NOFOLLOW_IMPORT_TO,
    "linux": LINUX_NOFOLLOW_IMPORT_TO,
    "macos": MACOS_NOFOLLOW_IMPORT_TO,
}


def get_os_name() -> str:
    """Return the normalized OS name used in PowerRules artifact names.

    Returns:
        One of "windows", "macos", or "linux".

    Raises:
        RuntimeError: If the current operating system is unsupported.
    """
    system_name = platform.system()

    if system_name == "Windows":
        return "windows"

    if system_name == "Darwin":
        return "macos"

    if system_name == "Linux":
        return "linux"

    raise RuntimeError(f"Unsupported operating system: {system_name}")


def get_arch_name() -> str:
    """Return the normalized architecture name used in PowerRules artifact names.

    Returns:
        The normalized machine architecture (e.g. "x86_64", "arm64").
    """
    architecture = platform.machine().lower()

    architecture_aliases = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }

    return architecture_aliases.get(architecture, architecture)


def build_windows_file_version(package_version: str) -> str:
    """Convert a PowerRules version into the four-part numeric format Windows requires.

    Beta suffixes (e.g. "1.2.3b4") are converted into a fourth numeric component shifted by one (e.g. "1.2.3.5"),
    since Windows file versions only support "X.Y.Z.W".
    The shift ensures that a first beta ("1.2.3b0") can be told apart from the stable release ("1.2.3.0").
    Anything after the version (e.g. ".post3.dev0+28b1684") is ignored.

    Args:
        package_version: The version reported by importlib.metadata.

    Returns:
        The version in "X.Y.Z.W" format.

    Raises:
        ValueError: If the version does not start with "X.Y.Z".
    """
    match = VERSION_PATTERN.match(package_version)

    if match is None:
        raise ValueError(f"Unsupported package version '{package_version}'")

    beta = match["beta"]
    fourth_component = int(beta) + 1 if beta is not None else 0

    return f"{match['base']}.{fourth_component}"


def build_nuitka_command(output_dir: Path, output_filename: str) -> list[str]:
    """Build the Nuitka command line for the current platform.

    Args:
        output_dir: Directory the resulting executable is written to.
        output_filename: File name of the resulting executable.

    Returns:
        The full Nuitka command line, ready to be executed.

    Raises:
        FileNotFoundError: If the icon for the current platform does not exist.
    """
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--python-flag=-m",
        "--assume-yes-for-downloads",
        f"--output-dir={output_dir}",
        f"--output-filename={output_filename}",
        "--include-distribution-metadata=powerrules",
        # Delete all build directories
        "--remove-output",
        # Write a compilation report file
        "--report=nuitka-compilation-report.xml",
    ]

    command += [f"--nofollow-import-to={module}" for module in NOFOLLOW_IMPORT_TO]
    command += [
        f"--nofollow-import-to={module}"
        for module in PLATFORM_NOFOLLOW_IMPORT_TO[get_os_name()]
    ]
    command += [f"--include-module={module}" for module in sorted(KEPT_MODULES)]

    icon_setting = PLATFORM_ICONS.get(get_os_name())
    if icon_setting is not None:
        icon_option, icon_filename = icon_setting
        icon_path = ICON_DIRECTORY / icon_filename
        # Fail early instead of silently building an executable without an icon
        if not icon_path.is_file():
            raise FileNotFoundError(f"Icon file not found: {icon_path}")
        command.append(f"{icon_option}={icon_path}")

    if get_os_name() == "windows":
        try:
            package_version = version("powerrules")
        except PackageNotFoundError:
            # Development environments without poetry-dynamic-versioning active
            package_version = "0.0.0.0"

        windows_file_version = build_windows_file_version(package_version)

        command += [
            # Requires Visual Studio Build Tools 2022 or later (GitHub Action runners should include it)
            "--msvc=latest",
            # Fails the build if the runtime DLLs are not present instead of silently omitting them
            "--include-windows-runtime-dlls=yes",
            f"--windows-file-version={windows_file_version}",
            # Windows does allow custom strings as product version, but nuitka denies them. It is what it is
            f"--windows-product-version={windows_file_version}",
            # The numeric version cannot express a beta, so the real version is part of the description
            f"--file-description=A rule-based command automation tool ({package_version})",
            "--copyright=https://github.com/LeoTN/PowerRules/blob/main/LICENSE",
            "--company-name=https://github.com/LeoTN/PowerRules",
            "--product-name=PowerRules",
        ]

    command.append(str(ENTRY_POINT))

    return command


def main() -> None:
    """Build a standalone PowerRules executable for the current platform."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory the executable is written to (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--expected-version",
        help="Fail if the built executable reports a different version (e.g. 1.2.3 != 1.2.3b4).",
    )
    arguments = parser.parse_args()

    os_name = get_os_name()
    arch_name = get_arch_name()
    output_dir = arguments.output_dir.resolve()
    output_filename = f"powerrules-{os_name}-{arch_name}"

    if os_name == "windows":
        output_filename += ".exe"

    output_full_path = output_dir / output_filename

    command = build_nuitka_command(
        output_dir=output_dir,
        output_filename=output_filename,
    )

    print(f"[INFO] Building {output_filename} with Nuitka...")

    subprocess.run(command, check=True, cwd=REPO_ROOT)

    print(f"[INFO] Build complete: {output_full_path}")

    # A simple call with --version verifies that the binary is compiled correctly
    print("[INFO] Testing binary with '--version'...")

    result = subprocess.run(
        [output_full_path, "--version"], check=True, capture_output=True, text=True
    )
    version_output = result.stdout.strip()

    if not re.match(r"^PowerRules \d", version_output):
        print(
            f"[ERROR] Binary verification failed due to unexpected --version output: {version_output}"
        )
        sys.exit(1)

    # Catches a binary which was built with the wrong version (e.g. the 0.0.0 placeholder)
    if arguments.expected_version is not None:
        expected_output = f"PowerRules {arguments.expected_version}"

        if version_output != expected_output:
            print(
                f"[ERROR] Binary verification failed due to unexpected version: expected '{expected_output}', got '{version_output}'"
            )
            sys.exit(1)

    print("[INFO] Running smoke tests...")
    failures = run_smoke_tests(output_full_path)

    if failures:
        for failure in failures:
            print(f"[ERROR] Smoke test failed: {failure}")
        sys.exit(1)

    print(f"[INFO] Binary verification successful: {version_output}")


if __name__ == "__main__":
    main()
