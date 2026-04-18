#!/usr/bin/env python3
"""
Static site builder entry point.

Usage:
    python build.py --config structure.json --output ./dist
    python build.py --config structure.json --output ./dist --recent 5
"""

import argparse
import sys
from sitebuilder.builder import SiteBuilder


def main():
    parser = argparse.ArgumentParser(description="Build a static site from a JSON structure.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the JSON structure file (e.g. structure.json)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory for the built site",
    )
    parser.add_argument(
        "--templates",
        default="templates",
        help="Directory containing HTML templates (default: templates/)",
    )
    parser.add_argument(
        "--stylesheets",
        default="stylesheets",
        help="Directory containing CSS stylesheets (default: stylesheets/)",
    )
    parser.add_argument(
        "--content-root",
        default="content",
        help="Root directory where content files live (default: content/)",
    )
    parser.add_argument(
        "--recent",
        type=int,
        default=5,
        help="Number of recently-built pages to surface in <!--INSERT RECENT PAGES HERE--> (default: 5)",
    )

    args = parser.parse_args()

    builder = SiteBuilder(
        config_path=args.config,
        output_dir=args.output,
        templates_dir=args.templates,
        stylesheets_dir=args.stylesheets,
        content_root=args.content_root,
        recent_count=args.recent,
    )
    builder.build()
    pass


if __name__ == "__main__":
    main()
    pass
