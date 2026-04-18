"""
Pandoc integration.

Converts source content files to HTML fragments using pandoc.
The content_type field in the JSON (e.g. "odt", "md", "html") determines
the pandoc --from flag.
"""

import logging
import shutil
import subprocess
from pathlib import Path

import os
import posixpath

logger = logging.getLogger(__name__)

# Map content_type values to pandoc --from reader names
READER_MAP = {
    "odt": "odt",
    "md": "markdown",
    "markdown": "markdown",
    "html": "html",
    "rst": "rst",
    "tex": "latex",
    "latex": "latex",
    "docx": "docx",
    # "plain" is not a valid pandoc input format; treat bare text as markdown
    # so the user can write simple flat prose without needing ODT.
    "txt": "markdown",
    "text": "markdown",
    "plain": "markdown",
}


def convert_content(content_path: str | Path, content_type: str, content_root: Path, media_out_root: Path) -> str:
    """
    Convert a content file to an HTML fragment via pandoc.

    Returns the HTML string, or an HTML comment explaining the failure.
    """
    if not content_path or str(content_path) == "path/to/file":
        return "<!-- No content file specified -->"

    full_path = content_root / content_path
    if not full_path.exists():
        logger.warning("Content file not found: %s", full_path)
        return f"<!-- Content file not found: {full_path} -->"

    if not shutil.which("pandoc"):
        logger.warning("pandoc not found on PATH; content will not be converted")
        return f"<!-- pandoc not available; would convert: {full_path} -->"

    reader = READER_MAP.get(content_type.lower(), content_type.lower())

    if reader == "html":
        return full_path.read_text(encoding="utf-8")

    current_directory = os.getcwd()
    try:
        os.chdir(media_out_root.resolve()) #this way files are extracted to a folder nearby the output
    except FileNotFoundError:
        os.chdir(media_out_root.resolve().parent)
    except NotADirectoryError:
        os.chdir(media_out_root.resolve().parent)

    try:
        result = subprocess.run(
            ["pandoc", "--from", reader, "--to", "html", str(full_path), "--extract-media", "media"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        logger.error("pandoc failed for %s: %s", full_path, exc.stderr)
        return f"<!-- pandoc error: {exc.stderr.strip()} -->"
    finally:
        os.chdir(current_directory) #always change it back
