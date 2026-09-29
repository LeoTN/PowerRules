"""Build a standalone PowerRules executable for the current platform using Nuitka.

Usage:
    poetry run python devscripts/build_executable.py [--output-dir DIR]
"""

import argparse
import platform
import re
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRY_POINT = REPO_ROOT / "src" / "powerrules"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "dist" / "executable"


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
        The machine architecture (e.g. "x86_64", "arm64").
    """
    return platform.machine().lower()


def build_windows_file_version(package_version: str) -> str:
    """Convert a PowerRules version into the four-part numeric format Windows requires.

    Beta suffixes (e.g. "1.2.3b4") are converted into a fourth numeric component
    (e.g. "1.2.3.4"), since Windows file versions only support "X.Y.Z.W".

    Args:
        package_version: The version reported by importlib.metadata.

    Returns:
        The version in "X.Y.Z.W" format.
    """
    base_version, _, beta_suffix = package_version.partition("b")
    beta_number = beta_suffix if beta_suffix else "0"

    return f"{base_version}.{beta_number}"


def build_nuitka_command(output_dir: Path, output_filename: str) -> list[str]:
    """Build the Nuitka command line for the current platform.

    Args:
        output_dir: Directory the resulting executable is written to.
        output_filename: File name of the resulting executable.

    Returns:
        The full Nuitka command line, ready to be executed.
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
    ]

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
            # Strings are allowed here
            f"--windows-product-version={package_version}",
            "--file-description=A rule-based computer power state management tool",
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
    arguments = parser.parse_args()

    os_name = get_os_name()
    arch_name = get_arch_name()
    output_filename = f"powerrules-{os_name}-{arch_name}"

    if os_name == "windows":
        output_filename += ".exe"

    output_full_path = arguments.output_dir / output_filename

    command = build_nuitka_command(
        output_dir=arguments.output_dir,
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

    print(f"[INFO] Binary verification successful: {version_output}")


if __name__ == "__main__":
    main()
