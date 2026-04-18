"""
Widget generation.

A widget is a small linked card that appears in directory listing pages,
containing: an image, a title, and a description — all linking to the
target page.

The builder is responsible for sorting nodes before passing them here.
"""

from .node import Node


def build_widget(node: Node) -> str:
    """Return the HTML for a single widget card."""
    url   = node.url
    title = node.widget_title
    desc  = node.widget_description
    img   = node.widget_image

    img_tag = ""
    if img and img != "path/to/file":
        img_tag = f'  <img src="{img}" alt="" class="widget__image">\n'

    return (
        f'<a href="{url}" class="widget">\n'
        f"{img_tag}"
        f'  <span class="widget__title">{title}</span>\n'
        f'  <span class="widget__desc">{desc}</span>\n'
        f"</a>\n"
    )


def build_widget_grid(nodes: list[Node]) -> str:
    """
    Return the HTML for a grid of widget cards.
    Nodes are rendered in the order given; the caller is responsible for
    sorting (typically date-descending via _sort_by_date in builder.py).
    """
    widgets = "".join(build_widget(n) for n in nodes)
    return f'<div class="widget-grid">\n{widgets}</div>'
