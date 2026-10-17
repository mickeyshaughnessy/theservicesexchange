#!/usr/bin/env python3
"""Refresh the Catalog block in index.html from demand-side apps in the site root.

The Grok bot writes those apps straight into the web root. They are not git
files. This script keeps the homepage links aligned with the files on disk.
A run that finds no apps leaves index.html unchanged.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
START = "<!-- demand-catalog:start -->"
END = "<!-- demand-catalog:end -->"

_TITLE = re.compile(r"<title>(.*?)</title>", re.I | re.S)


def discover(root: Path) -> list[dict]:
    apps = []
    for path in sorted(root.glob("*.html")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "submit_bid" not in text or "navbar-brand" in text:
            continue
        match = _TITLE.search(text)
        if not match:
            continue
        title = html.unescape(re.sub(r"\s+", " ", match.group(1)).strip())
        if "—" not in title:
            continue
        name, job = (part.strip() for part in title.split("—", 1))
        if not name or not job:
            continue
        if name.lower() in {"the rse", "the robot services exchange"}:
            continue
        apps.append({"href": "/" + path.name, "name": name, "job": job})
    apps.sort(key=lambda app: app["name"].casefold())
    return apps


def render(apps: list[dict]) -> str:
    lines = ['<div class="demand-catalog">']
    for app in apps:
        name = html.escape(app["name"])
        job = html.escape(app["job"])
        href = html.escape(app["href"], quote=True)
        lines.append(
            f'  <a class="demand-catalog-link" href="{href}">'
            f'<span class="demand-catalog-name">{name}</span>'
            f'<span class="demand-catalog-job">{job}</span></a>'
        )
    lines.append("</div>")
    return "\n".join(lines)


def replace_block(source: str, block: str) -> str:
    start = source.find(START)
    end = source.find(END)
    if start == -1 or end == -1 or end < start:
        raise SystemExit("index.html is missing the demand-catalog markers")
    end += len(END)
    return source[:start] + START + "\n" + block + "\n" + END + source[end:]


def main() -> int:
    apps = discover(ROOT)
    if not apps:
        print("no demand apps found; catalog unchanged")
        return 0
    source = INDEX.read_text(encoding="utf-8")
    updated = replace_block(source, render(apps))
    if updated != source:
        INDEX.write_text(updated, encoding="utf-8")
        print(f"catalog updated ({len(apps)} apps)")
    else:
        print(f"catalog already current ({len(apps)} apps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
