"""
Node: a single page (or directory index) in the site tree.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class Node:
    key: str           # Original JSON key (e.g. "test_story")
    slug: str          # URL/filesystem slug (e.g. "teststory")
    url_path: list     # List of path segments from root (e.g. ["writing", "fiction", "teststory"])
    fs_path: Path      # Filesystem path for the output file/directory
    data: dict         # The raw JSON object for this page
    is_directory: bool # True if this is a section index page

    # Set after the page file is written
    out_file: Path = field(default=None, init=False)

    @property
    def date(self) -> date | None:
        """
        Parse the optional "date" field (DDMMYYYY) into a date object.
        Returns None if absent or malformed.
        """
        raw = self.data.get("date")
        if not raw:
            return None
        raw = str(raw).strip()
        if len(raw) != 8 or not raw.isdigit():
            return None
        try:
            return date(int(raw[4:]), int(raw[2:4]), int(raw[:2]))
        except ValueError:
            return None

    @property
    def url(self) -> str:
        segments = "/".join(self.url_path)
        if not segments:
            return "/"
        if self.is_directory:
            return "/" + segments + "/"
        return "/" + segments

    @property
    def template(self) -> str:
        return self.data.get("template", "default")

    @property
    def stylesheet(self) -> str | None:
        return self.data.get("stylesheet")

    @property
    def title(self) -> str:
        return self.data.get("title", self.key)

    @property
    def icon(self) -> str | None:
        return self.data.get("icon")

    @property
    def content_path(self) -> str | None:
        return self.data.get("content")

    @property
    def content_type(self) -> str | None:
        return self.data.get("content_type")

    # Widget fields
    @property
    def widget_image(self) -> str | None:
        return self.data.get("widget_image")

    @property
    def widget_title(self) -> str:
        return self.data.get("widget_title", self.key)

    @property
    def widget_description(self) -> str:
        return self.data.get("widget_description", "")
