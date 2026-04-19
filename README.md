# sitebuilder

A Python static site generator driven by a JSON structure file.

## Project layout

```
sitebuilder/
├── build.py                  # CLI entry point
├── README.md
└── sitebuilder/
    ├── __init__.py
    ├── builder.py            # Orchestrator — walks the JSON tree
    ├── node.py               # Dataclass representing one page
    ├── renderer.py           # Template loading & placeholder substitution
    ├── pandoc.py             # pandoc wrapper (content → HTML fragment)
    └── widgets.py            # Widget card HTML generation
```

## Requirements

- Python 3.11+
- [pandoc](https://pandoc.org/) on your `PATH` (for content conversion)

## Usage

```bash
python build.py \
  --config   structure.json \
  --output   dist/ \
  --templates   templates/ \
  --stylesheets stylesheets/ \
  --content-root content/ \
  --recent 5
```

All flags except `--config` and `--output` have defaults (shown above).

## How it works

### JSON structure

Each key in the JSON is either:

- **A leaf page** — `"is_page": true` with optional template, stylesheet,
  widget fields, and content fields.
- **A section node** — `"is_page": false`, with an optional `"index"` sub-object
  (the directory index page) and a `"contents"` sub-object (child pages/sections).

The root object may also contain an `"index"` key for the site's home page.

In the example JSON structure file included, you can see that the "writing" directory specifies defaults which are not overridden in the first entry in its contents. This saves time when writing the structure out.

### Slugs / URLs

Keys are slugified by stripping underscores and spaces:

| Key          | Slug / URL segment |
|--------------|--------------------|
| `test_story` | `teststory`        |
| `05042026`   | `05042026`         |
| `writing`    | `writing`          |

Leaf pages are written as extensionless files, e.g. `dist/writing/fiction/teststory`.
Directory index pages are written as `dist/writing/index`.

Your web server should be configured to serve extensionless files and directory
indexes without the `/index` suffix (standard Apache/nginx behaviour).

### Templates

Templates live in `templates/` as `<name>.html`, e.g. `templates/story.html`.
A template is a complete HTML document containing placeholder comments:

| Placeholder                       | Replaced with                                      |
|-----------------------------------|----------------------------------------------------|
| `<!--INSERT CONTENT HERE-->`      | Body HTML produced by pandoc from the content file |
| `<!--INSERT STYLESHEET HERE-->`   | `<link>` tag for the page stylesheet               |
| `<!--INSERT TITLE HERE-->`        | Page `<title>` value                               |
| `<!--INSERT ICON HERE-->`         | Favicon `<link>` tag                               |
| `<!--INSERT CANONICAL HERE-->`    | Canonical URL `<link>` tag                         |
| `<!--INSERT WIDGETS HERE-->`      | Widget grid of child pages (directory pages)       |
| `<!--INSERT RECENT PAGES HERE-->` | n most recently-built leaf pages                   |
| `<!--INSERT DIRECTORIES HERE-->`  | Top-level section links                            |

If a template file is missing, a plain built-in fallback is used.

### Stylesheets

Stylesheet filenames are derived from the `"stylesheet"` field:

```json
"stylesheet": "directorystyle"
```

resolves to `stylesheets/directorystyle.css`, injected as a root-relative `<link>`.

### Content files

The `"content"` field is a path relative to `--content-root`.
The `"content_type"` field is passed to pandoc as the reader format:

| `content_type` | pandoc reader |
|----------------|---------------|
| `odt`          | `odt`         |
| `md`           | `markdown`    |
| `html`         | `html`        |
| `rst`          | `rst`         |
| `tex`          | `latex`       |
| `docx`         | `docx`        |
| `txt`          | `plain`       |

### Widgets

A widget is a linked card (`<a class="widget">`) containing an image, title,
and description. They are generated automatically for directory index pages
from the child pages' widget fields, displayed newest-first (reverse
encounter order).

### Recent pages

`<!--INSERT RECENT PAGES HERE-->` is replaced with the _n_ most recently built
leaf pages (not directory indexes), where _n_ is set by `--recent` (default 5).
"Recently built" means "encountered later in a depth-first walk of the JSON",
which corresponds to the order entries appear in your JSON file.

### Top-level directories

`<!--INSERT DIRECTORIES HERE-->` is replaced with links to all top-level
section index pages (those one level deep, e.g. `/writing`, `/diary`).
