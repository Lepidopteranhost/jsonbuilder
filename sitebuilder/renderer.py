"""
Renderer: loads an HTML template and fills every placeholder it contains.

Placeholders handled here (first pass):
  <!--INSERT CONTENT HERE-->          — converted body content via pandoc
  <!--INSERT STYLESHEET HERE-->       — <link> tag for the page stylesheet
  <!--INSERT TITLE HERE-->            — page <title> value
  <!--INSERT ICON HERE-->             — favicon <link> tag
  <!--INSERT WIDGETS HERE-->          — widget grid for directory pages
  <!--INSERT CANONICAL HERE-->        — canonical URL <link>

Placeholders resolved in the builder's second pass (left intact here):
  <!--INSERT RECENT PAGES HERE-->
  <!--INSERT DIRECTORIES HERE-->

The renderer reads templates from the ORIGINAL templates_dir (source), and
generates stylesheet <link> hrefs that point to the COPY inside the output
directory (out_stylesheets_dir), expressed as a root-relative URL.
"""

import logging
from pathlib import Path

from .node import Node
from .pandoc import convert_content
from .widgets import build_widget_grid

logger = logging.getLogger(__name__)

PLACEHOLDER_CONTENT    = "<!--INSERT CONTENT HERE-->"
PLACEHOLDER_STYLESHEET = "<!--INSERT STYLESHEET HERE-->"
PLACEHOLDER_TITLE      = "<!--INSERT TITLE HERE-->"
PLACEHOLDER_ICON       = "<!--INSERT ICON HERE-->"
PLACEHOLDER_WIDGETS    = "<!--INSERT WIDGETS HERE-->"
PLACEHOLDER_CANONICAL  = "<!--INSERT CANONICAL HERE-->"

# Sentinel left in the HTML so the builder can inject widgets in a second step
_WIDGET_SENTINEL = "<!-- widgets injected at build time -->"


class Renderer:
    def __init__(self, templates_dir: Path, out_stylesheets_dir: Path):
        """
        templates_dir       — where the source .html template files live
        out_stylesheets_dir — where stylesheets will be copied to inside the
                              output directory; used to build root-relative hrefs
        """
        self.templates_dir      = templates_dir
        self.out_stylesheets_dir = out_stylesheets_dir

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def render(self, node: Node, content_root: Path) -> str:
        """Return partially-rendered HTML for the given node.

        The WIDGETS placeholder is replaced with a sentinel; the builder
        calls inject_widgets() afterwards once it knows the child nodes.
        RECENT and DIRECTORIES placeholders are left as-is for the global
        second pass.
        """
        html = self._load_template(node.template)

        html = html.replace(PLACEHOLDER_STYLESHEET, self._stylesheet_tag(node))
        html = html.replace(PLACEHOLDER_TITLE,      node.title)
        html = html.replace(PLACEHOLDER_ICON,       self._icon_tag(node))
        html = html.replace(PLACEHOLDER_CANONICAL,  f'<link rel="canonical" href="{node.url}">')
        html = html.replace(PLACEHOLDER_CONTENT,    convert_content(
                                                        node.content_path,
                                                        node.content_type or "html",
                                                        content_root,
                                                        node.fs_path,
                                                    ))
        html = html.replace(PLACEHOLDER_WIDGETS,    _WIDGET_SENTINEL)

        return html

    def inject_widgets(self, html: str, widget_html: str) -> str:
        """Replace the widget sentinel with actual widget HTML."""
        return html.replace(_WIDGET_SENTINEL, widget_html)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_template(self, template_name: str) -> str:
        """Load a template file from the source templates directory.
        Falls back to a bare-bones built-in if the file is missing."""
        path = self.templates_dir / f"{template_name}.html"
        if path.exists():
            return path.read_text(encoding="utf-8")

        logger.warning("Template not found: %s — using built-in fallback", path)
        return self._fallback_template()

    def _stylesheet_tag(self, node: Node) -> str:
        if not node.stylesheet:
            return ""
        # Root-relative href pointing at the COPY inside the output dir.
        # out_stylesheets_dir is e.g. /some/output/stylesheets; we want
        # just the last two components: stylesheets/<name>.css
        rel = f"{self.out_stylesheets_dir.name}/{node.stylesheet}.css"
        return f'<link rel="stylesheet" href="/{rel}">'

    def _icon_tag(self, node: Node) -> str:
        icon = node.icon
        if not icon or icon == "path/to/file":
            return ""
        return f'<link rel="icon" href="{icon}">'

    # ------------------------------------------------------------------
    # Fallback template
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_template() -> str:
        return """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <!--INSERT ICON HERE-->
  <!--INSERT STYLESHEET HERE-->
  <!--INSERT CANONICAL HERE-->
  <title><!--INSERT TITLE HERE--></title>
</head>
<body>
  <nav>
    <div class="directories">
      <!--INSERT DIRECTORIES HERE-->
    </div>
  </nav>

  <main>
    <div class="content">
      <!--INSERT CONTENT HERE-->
    </div>

    <div class="widgets">
      <!--INSERT WIDGETS HERE-->
    </div>
  </main>

  <aside>
    <div class="recent-pages">
      <!--INSERT RECENT PAGES HERE-->
    </div>
  </aside>
</body>
</html>
"""
