"""Export the executable icon master SVG to PNG or ICO files.

Every size is rendered directly from the vector master with the Inkscape command line, so no raster scaling takes place.
The ICO containers are written with the standard library only (PNG-compressed entries),
which means no additional Python dependencies are required.

Usage:
    poetry run python devscripts/export_executable_icons.py [--inkscape PATH]
"""

import argparse
import logging
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE: Final[Path] = REPO_ROOT / "assets" / "icon" / "executable_icon.svg"
DEFAULT_OUTPUT_DIR: Final[Path] = REPO_ROOT / "assets" / "icon"
DEFAULT_INKSCAPE_PATH: Final[Path] = Path("C:/Program Files/Inkscape/bin/inkscape.com")

ICO_SIZES: Final[tuple[int, ...]] = (16, 24, 32, 48, 64, 128, 256)
LINUX_PNG_SIZE: Final[int] = 512
INKSCAPE_TIMEOUT_SECONDS: Final[int] = 60


def find_inkscape(explicit_path: Path | None) -> Path:
    """Return the Inkscape executable to use.

    The lookup order is the explicit path, the PATH and finally the default installation path.

    Args:
        explicit_path: Optional path given by the user, takes precedence over every other lookup.

    Raises:
        FileNotFoundError: If no usable Inkscape executable can be found.
    """
    if explicit_path is not None:
        if not explicit_path.is_file():
            raise FileNotFoundError(f"Inkscape executable not found: {explicit_path}")
        return explicit_path

    found = shutil.which("inkscape")
    if found is not None:
        return Path(found)

    if DEFAULT_INKSCAPE_PATH.is_file():
        return DEFAULT_INKSCAPE_PATH

    raise FileNotFoundError(
        "Inkscape not found on PATH or at the default location, use --inkscape to specify the executable"
    )


def render_png(inkscape: Path, source: Path, size: int, target: Path) -> bytes:
    """Render the SVG as a square transparent PNG and return its bytes.

    Raises:
        RuntimeError: If Inkscape fails or does not produce the expected file.
    """
    command = [
        str(inkscape),
        str(source),
        "--export-type=png",
        f"--export-filename={target}",
        f"--export-width={size}",
        f"--export-height={size}",
        "--export-area-page",
        "--export-background-opacity=0",
    ]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=INKSCAPE_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"Inkscape failed for size {size}: {error.stderr.strip()}"
        ) from error

    if not target.is_file():
        raise RuntimeError(
            f"Inkscape did not create the expected file for size {size}: {target}"
        )
    return target.read_bytes()


def build_ico(images: dict[int, bytes]) -> bytes:
    """Build an ICO container from PNG images keyed by their pixel size."""
    sizes = sorted(ICO_SIZES)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = len(header) + 16 * len(sizes)

    directory = b""
    payload = b""
    for size in sizes:
        data = images[size]
        # A width/height byte of 0 means 256 pixels
        dimension = 0 if size >= 256 else size
        directory += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset
        )
        payload += data
        offset += len(data)
    return header + directory + payload


def export_executable_icons(source: Path, output_dir: Path, inkscape: Path) -> None:
    """Render all required sizes and write the PNG or ICO files.

    Raises:
        FileNotFoundError: If the source SVG does not exist.
        RuntimeError: If rendering a size fails.
    """
    if not source.is_file():
        raise FileNotFoundError(f"Source SVG not found: {source}")

    sizes = sorted({*ICO_SIZES, LINUX_PNG_SIZE})
    images: dict[int, bytes] = {}
    with tempfile.TemporaryDirectory() as temp_name:
        temp_dir = Path(temp_name)
        for size in sizes:
            logger.info(f"Rendering {size}x{size} PNG")
            images[size] = render_png(
                inkscape, source, size, temp_dir / f"icon_{size}.png"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        output_dir / f"{source.stem}.ico": build_ico(images),
        output_dir / f"{source.stem}.png": images[LINUX_PNG_SIZE],
    }
    for path, data in outputs.items():
        path.write_bytes(data)
        logger.info(f"Wrote {path} ({len(data)} bytes)")


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the export and return the process exit code."""
    parser = argparse.ArgumentParser(
        description="Export executable icons from the SVG master"
    )
    parser.add_argument(
        "--source", type=Path, default=DEFAULT_SOURCE, help="path to the master SVG"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory for the icon files",
    )
    parser.add_argument(
        "--inkscape",
        type=Path,
        default=None,
        help="path to the Inkscape executable (default: PATH lookup, then the default installation path)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    try:
        inkscape = find_inkscape(args.inkscape)
        export_executable_icons(args.source, args.output_dir, inkscape)
    except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as error:
        logger.error(f"Icon export failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
