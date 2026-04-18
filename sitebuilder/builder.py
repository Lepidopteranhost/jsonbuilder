"""
SiteBuilder: orchestrates the full build.

Walk the JSON tree, and for every node that is a page (is_page: true),
produce a file in the output directory. After all pages have been built,
make a second pass to fill in the <!--INSERT RECENT PAGES HERE--> and
<!--INSERT DIRECTORIES HERE--> placeholders that could not be resolved
on the first pass.
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

        # Copy asset directories into the output directory so the whole
        # output tree is self-contained and ready for SFTP transfer.
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

        # Recurse into the rest of the tree
        rest = {k: v for k, v in self.config.items() if k != "index"}
        self._parse_tree(rest, url_path=[], fs_path=self.output_dir)

        # Second pass: global placeholders now that built_pages is complete
        self._resolve_placeholders()

        logger.info("Build complete. %d pages generated.", len(self.built_pages))

    # ------------------------------------------------------------------
    # Asset copying
    # ------------------------------------------------------------------

    def _copy_assets(self):
        """
        Mirror templates and stylesheets into the output directory.
        The output directory will therefore contain everything needed to
        serve the site from a remote machine with no local source files.
        """
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
    ) -> list[Node]:
        """
        Recursively walk the config tree.
        Returns all Node objects created at ANY depth (for built_pages tracking).
        Widget lists are built from direct children only — see below.
        """
        all_nodes: list[Node] = []

        for key, value in tree.items():
            if not isinstance(value, dict):
                continue

            slug = _slugify(key)
            child_url = url_path + [slug]
            child_fs  = fs_path / slug

            is_page = value.get("is_page", False)

            if is_page:
                # ---- Leaf page ----
                child_fs.parent.mkdir(parents=True, exist_ok=True)
                node = Node(
                    key=key,
                    slug=slug,
                    url_path=child_url,
                    fs_path=child_fs,
                    data=value,
                    is_directory=False,
                )
                self._build_page(node, children=[])
                self.built_pages.append(node)
                all_nodes.append(node)

            else:
                # ---- Section node ----
                # Don't create the directory yet — only do so if the section
                # actually has an index page or child content to emit.

                # Recurse into contents one key at a time so we can distinguish
                # direct children (for this directory's widget grid) from deeper
                # descendants (only needed for built_pages tracking).
                #
                # direct_children: the "top" node for each immediate child entry —
                #   a leaf node if the child is is_page:true, or the child
                #   section's own index node if it has one. These go in widgets.
                # all_nodes: every node at any depth, so built_pages stays complete.
                direct_children: list[Node] = []
                contents = value.get("contents")
                if contents and isinstance(contents, dict):
                    child_fs.mkdir(parents=True, exist_ok=True)
                    for child_key, child_value in contents.items():
                        if not isinstance(child_value, dict):
                            continue
                        # Parse this single child entry; returns its nodes
                        # in the same order _parse_tree always uses:
                        # leaves first, then the section index at the end.
                        child_nodes = self._parse_tree(
                            {child_key: child_value}, child_url, child_fs
                        )
                        all_nodes.extend(child_nodes)
                        # The representative node for widget purposes:
                        # - leaf page  → first (and only) node
                        # - section    → last node (the index page, appended after
                        #                its descendants in _parse_tree)
                        if child_nodes:
                            child_is_page = child_value.get("is_page", False)
                            if child_is_page:
                                direct_children.append(child_nodes[0])
                            else:
                                # Section: its index is the last node returned
                                direct_children.append(child_nodes[-1])

                # Build the directory index page
                index_data = value.get("index")
                if index_data and isinstance(index_data, dict) and index_data.get("is_page"):
                    child_fs.mkdir(parents=True, exist_ok=True)
                    index_node = Node(
                        key=key,
                        slug=slug,
                        url_path=child_url,
                        fs_path=child_fs,
                        data=index_data,
                        is_directory=True,
                    )
                    # Widget grid: direct children only, sorted by date descending
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
        logger.info("Building: /%s", "/".join(node.url_path))

        html = self.renderer.render(node, self.content_root)

        # Inject child widgets (directory pages only)
        if node.is_directory and children:
            widget_html = build_widget_grid(children)
            html = self.renderer.inject_widgets(html, widget_html)

        # Choose output path
        if node.is_directory:
            # e.g. dist/writing/index.html
            out_file = node.fs_path / "index.html"
        else:
            out_file = node.fs_path.with_suffix(".html")

        out_file.write_text(html, encoding="utf-8")
        node.out_file = out_file

    # ------------------------------------------------------------------
    # Second-pass placeholder resolution
    # ------------------------------------------------------------------

    def _resolve_placeholders(self):
        """
        Fill in global placeholders that depend on the full page list:
          <!--INSERT RECENT PAGES HERE-->
          <!--INSERT DIRECTORIES HERE-->
        """
        recent_html = self._build_recent_html()
        dirs_html   = self._build_dirs_html()

        for node in self.built_pages:
            if not getattr(node, "out_file", None) or not node.out_file.exists():
                continue

            text = node.out_file.read_text(encoding="utf-8")
            changed = False

            if "<!--INSERT RECENT PAGES HERE-->" in text:
                text = text.replace("<!--INSERT RECENT PAGES HERE-->", recent_html)
                changed = True
            if "<!--INSERT DIRECTORIES HERE-->" in text:
                text = text.replace("<!--INSERT DIRECTORIES HERE-->", dirs_html)
                changed = True

            if changed:
                node.out_file.write_text(text, encoding="utf-8")

    # ------------------------------------------------------------------
    # HTML snippet builders
    # ------------------------------------------------------------------

    def _build_recent_html(self) -> str:
        """
        n most recently dated leaf pages, newest first.
        Pages with a "date" field are sorted by that date (DDMMYYYY).
        Undated pages follow, in the order they were built.
        """
        leaf_pages = [p for p in self.built_pages if not p.is_directory]
        dated   = sorted([p for p in leaf_pages if p.date], key=lambda p: p.date, reverse=True)
        undated = [p for p in leaf_pages if not p.date]
        ordered = (dated + undated)[: self.recent_count]

        if not ordered:
            return ""

        items = "<br>".join(_dir_widget_link(p, css_prefix="recent-widget") for p in ordered)
        return f'<div class="recent-pages">\n{items}</div>'

    def _build_dirs_html(self) -> str:
        """Links to top-level section index pages (depth == 1)."""
        top_dirs = [p for p in self.built_pages if p.is_directory and len(p.url_path) == 1]

        if not top_dirs:
            return ""

        items = "<br>".join(_dir_widget_link(p, css_prefix="dir-widget") for p in top_dirs)
        return f'<div class="directories">\n{items}</div>'


# ------------------------------------------------------------------
# Module-level utilities
# ------------------------------------------------------------------

def _slugify(key: str) -> str:
    """Remove underscores and spaces to form an extensionless URL slug."""
    return key.replace("_", "").replace(" ", "")


def _valid_path(path: str) -> bool:
    return bool(path) and path != "path/to/file"


def _sort_by_date(nodes: list[Node]) -> list[Node]:
    """Sort nodes by date descending; undated nodes go to the end."""
    dated   = sorted([n for n in nodes if n.date], key=lambda n: n.date, reverse=True)
    undated = [n for n in nodes if not n.date]
    return dated + undated


def _widget_link(node: Node, css_prefix: str) -> str:
    title = node.data.get("widget_title") or node.data.get("title") or node.key
    desc  = node.data.get("widget_description", "")
    img   = node.data.get("widget_image", "")
    img_tag = (
        f'<img src="{img}" alt="" class="{css_prefix}__image">'
        if _valid_path(img) else ""
    )
    return (
        f'<a href="{node.url}" class="{css_prefix}">'
        f"{img_tag}"
        f'<span class="{css_prefix}__title">{title}</span>'
        f'<span class="{css_prefix}__desc">{desc}</span>'
        f"</a>\n"
    )


def _dir_widget_link(node: Node, css_prefix: str) -> str:
    title = node.data.get("widget_title") or node.data.get("title") or node.key
    img   = node.data.get("widget_image", "")
    img_tag = (
        f'<img src="{img}" alt="" class="{css_prefix}__image">'
        if _valid_path(img) else ""
    )
    return (
        f'<a href="{node.url}" class="{css_prefix}">'
        f"{img_tag}"
        f'<span class="{css_prefix}__title">{title}</span>'
        f"</a>\n"
    )
