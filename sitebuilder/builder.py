"""
SiteBuilder: orchestrates the full build.

Walk the JSON tree, and for every node that is a page (is_page: true),
produce a file in the output directory. After all pages have been built,
make a second pass to fill in the <!--INSERT RECENT PAGES HERE--> and
<!--INSERT DIRECTORIES HERE--> placeholders that could not be resolved
on the first pass.

Inheritance
-----------
Keys placed directly on a section node (alongside "is_page", "index",
"contents") are treated as defaults for all descendants.  A child may
override any inherited key simply by specifying it explicitly.  Inheritance
is transitive: a sub-section can itself carry defaults that propagate
further down.

Structural keys that are never inherited:
    is_page, index, contents, date,
    widget_title, widget_description
"""

import json
import logging
import shutil
from pathlib import Path

from .node import Node
from .renderer import Renderer
from .widgets import build_widget_grid

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

# Names of the asset sub-directories as they will appear inside the output dir
TEMPLATES_DEST   = "templates"
STYLESHEETS_DEST = "stylesheets"

# Keys that live on a section node but must never be pushed down to children
_STRUCTURAL_KEYS = {"is_page", "index", "contents"}

# Keys that are always page-specific and must never be inherited
_NON_INHERITABLE_KEYS = {"date", "widget_title", "widget_description"}

_SKIP_KEYS = _STRUCTURAL_KEYS | _NON_INHERITABLE_KEYS


def _extract_defaults(section: dict) -> dict:
    """Return the inheritable key/value pairs from a section node."""
    return {k: v for k, v in section.items() if k not in _SKIP_KEYS}


def _apply_defaults(data: dict, defaults: dict) -> dict:
    """
    Return a copy of *data* with *defaults* filled in for any missing keys.
    The child's own values always win.
    """
    merged = {**defaults, **data}
    return merged


class SiteBuilder:
    def __init__(
        self,
        config_path: str,
        output_dir: str,
        templates_dir: str = "templates",
        stylesheets_dir: str = "stylesheets",
        content_root: str = "content",
        recent_count: int = 5,
    ):
        self.config_path     = Path(config_path)
        self.output_dir      = Path(output_dir)
        self.templates_dir   = Path(templates_dir)
        self.stylesheets_dir = Path(stylesheets_dir)
        self.content_root    = Path(content_root)
        self.recent_count    = recent_count

        with open(self.config_path) as f:
            self.config = json.load(f)

        # All pages built so far, in encounter order (leaf pages before their
        # parent directory index — because we recurse into contents first).
        self.built_pages: list[Node] = []

        # Destination paths for assets inside the output directory
        self.out_templates_dir   = self.output_dir / TEMPLATES_DEST
        self.out_stylesheets_dir = self.output_dir / STYLESHEETS_DEST

        self.renderer = Renderer(
            templates_dir=self.templates_dir,
            out_stylesheets_dir=self.out_stylesheets_dir,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self):
        logger.info("Starting build → %s", self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._copy_assets()

        # Root index page (special: lives at /, not inside a slug dir)
        index_data = self.config.get("index")
        if index_data and isinstance(index_data, dict) and index_data.get("is_page"):
            index_node = Node(
                key="index",
                slug="",
                url_path=[],
                fs_path=self.output_dir,
                data=index_data,
                is_directory=True,
            )
            self._build_page(index_node, children=[])
            self.built_pages.append(index_node)

        # Recurse into the rest of the tree with an empty inherited defaults dict
        rest = {k: v for k, v in self.config.items() if k != "index"}
        self._parse_tree(rest, url_path=[], fs_path=self.output_dir, inherited={})

        self._resolve_placeholders()

        logger.info("Build complete. %d pages generated.", len(self.built_pages))

    # ------------------------------------------------------------------
    # Asset copying
    # ------------------------------------------------------------------

    def _copy_assets(self):
        self._mirror_dir(self.templates_dir,   self.out_templates_dir,   "templates")
        self._mirror_dir(self.stylesheets_dir, self.out_stylesheets_dir, "stylesheets")

    @staticmethod
    def _mirror_dir(src: Path, dst: Path, label: str):
        if not src.exists():
            logger.warning("%s directory not found: %s — skipping copy", label, src)
            return
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        logger.info("Copied %s → %s", src, dst)

    # ------------------------------------------------------------------
    # Tree parsing
    # ------------------------------------------------------------------

    def _parse_tree(
        self,
        tree: dict,
        url_path: list[str],
        fs_path: Path,
        inherited: dict,
    ) -> list[Node]:
        """
        Recursively walk the config tree.

        *inherited* carries the default key/value pairs passed down from
        ancestor section nodes.  Each section may extend or override these
        for its own descendants.
        """
        all_nodes: list[Node] = []

        for key, value in tree.items():
            if not isinstance(value, dict):
                continue

            slug      = _slugify(key)
            child_url = url_path + [slug]
            child_fs  = fs_path / slug

            is_page = value.get("is_page", False)

            if is_page:
                # ---- Leaf page ----
                # Merge inherited defaults; child's own keys take priority.
                resolved = _apply_defaults(value, inherited)

                child_fs.parent.mkdir(parents=True, exist_ok=True)
                node = Node(
                    key=key,
                    slug=slug,
                    url_path=child_url,
                    fs_path=child_fs,
                    data=resolved,
                    is_directory=False,
                )
                self._build_page(node, children=[])
                self.built_pages.append(node)
                all_nodes.append(node)

            else:
                # ---- Section node ----
                # Collect any defaults this section declares for its children,
                # layered on top of whatever was already inherited.
                section_defaults = _extract_defaults(value)
                child_inherited  = {**inherited, **section_defaults}

                # Recurse into contents one key at a time (to track direct
                # children separately from deeper descendants for widgets).
                direct_children: list[Node] = []
                contents = value.get("contents")
                if contents and isinstance(contents, dict):
                    child_fs.mkdir(parents=True, exist_ok=True)
                    for child_key, child_value in contents.items():
                        if not isinstance(child_value, dict):
                            continue
                        child_nodes = self._parse_tree(
                            {child_key: child_value},
                            child_url,
                            child_fs,
                            child_inherited,
                        )
                        all_nodes.extend(child_nodes)
                        if child_nodes:
                            child_is_page = child_value.get("is_page", False)
                            if child_is_page:
                                direct_children.append(child_nodes[0])
                            else:
                                direct_children.append(child_nodes[-1])

                # Build the directory index page.
                # The index itself also inherits from the section, but its own
                # keys override — same as any other child page.
                index_data = value.get("index")
                if index_data and isinstance(index_data, dict) and index_data.get("is_page"):
                    child_fs.mkdir(parents=True, exist_ok=True)
                    resolved_index = _apply_defaults(index_data, inherited)
                    index_node = Node(
                        key=key,
                        slug=slug,
                        url_path=child_url,
                        fs_path=child_fs,
                        data=resolved_index,
                        is_directory=True,
                    )
                    widget_children = _sort_by_date(direct_children)
                    self._build_page(index_node, children=widget_children)
                    self.built_pages.append(index_node)
                    all_nodes.append(index_node)

        return all_nodes

    # ------------------------------------------------------------------
    # Page building
    # ------------------------------------------------------------------

    def _build_page(self, node: Node, children: list[Node]):
        """Produce the output file for a single page node."""
        logger.info("Building: %s", node.url)

        html = self.renderer.render(node, self.content_root)

        if node.is_directory and children:
            widget_html = build_widget_grid(children)
            html = self.renderer.inject_widgets(html, widget_html)

        if node.is_directory:
            out_file = node.fs_path / "index.html"
        else:
            out_file = node.fs_path.with_suffix(".html")

        out_file.write_text(html, encoding="utf-8")
        node.out_file = out_file

    # ------------------------------------------------------------------
    # Second-pass placeholder resolution
    # ------------------------------------------------------------------

    def _resolve_placeholders(self):
        recent_html = self._build_recent_html()
        dirs_html   = self._build_dirs_html()

        for node in self.built_pages:
            if not getattr(node, "out_file", None) or not node.out_file.exists():
                continue

            text    = node.out_file.read_text(encoding="utf-8")
            changed = False

            if "<!--INSERT RECENT PAGES HERE-->" in text:
                text    = text.replace("<!--INSERT RECENT PAGES HERE-->", recent_html)
                changed = True
            if "<!--INSERT DIRECTORIES HERE-->" in text:
                text    = text.replace("<!--INSERT DIRECTORIES HERE-->", dirs_html)
                changed = True

            if changed:
                node.out_file.write_text(text, encoding="utf-8")

    # ------------------------------------------------------------------
    # HTML snippet builders
    # ------------------------------------------------------------------

    def _build_recent_html(self) -> str:
        leaf_pages = [p for p in self.built_pages if not p.is_directory]
        dated      = sorted([p for p in leaf_pages if p.date], key=lambda p: p.date, reverse=True)
        undated    = [p for p in leaf_pages if not p.date]
        ordered    = (dated + undated)[: self.recent_count]

        if not ordered:
            return ""

        items = "<br>\n".join(_widget_link(p, css_prefix="recent-widget") for p in ordered)
        return f'<div class="recent-pages">\n{items}\n</div>'

    def _build_dirs_html(self) -> str:
        top_dirs = [p for p in self.built_pages if p.is_directory and len(p.url_path) == 1]

        if not top_dirs:
            return ""

        items = "<br>\n".join(_widget_link(p, css_prefix="dir-widget") for p in top_dirs)
        return f'<div class="directories">\n{items}\n</div>'


# ------------------------------------------------------------------
# Module-level utilities
# ------------------------------------------------------------------

def _slugify(key: str) -> str:
    """Remove underscores and spaces to form a URL slug."""
    return key.replace("_", "").replace(" ", "")


def _valid_path(path: str) -> bool:
    return bool(path) and path != "path/to/file"


def _sort_by_date(nodes: list[Node]) -> list[Node]:
    dated   = sorted([n for n in nodes if n.date], key=lambda n: n.date, reverse=True)
    undated = [n for n in nodes if not n.date]
    return dated + undated


def _widget_link(node: Node, css_prefix: str) -> str:
    title   = node.data.get("widget_title") or node.data.get("title") or node.key
    img     = node.data.get("widget_image", "")
    img_tag = (
        f'<img src="{img}" alt="" class="{css_prefix}__image">'
        if _valid_path(img) else ""
    )
    return (
        f'<a href="{node.url}" class="{css_prefix}">'
        f"{img_tag}"
        f'<span class="{css_prefix}__title">{title}</span>'
        f"</a>"
    )
