#!/usr/bin/env python3
"""Check relative links in every .md file of the course.

    python3 scripts/check_links.py

For each [text](target), ![alt](target) and [label]: target outside code
blocks: the file or folder must exist, and an #anchor must match a heading
of the target file (GitHub slug rules). External links (http, mailto) are
skipped. Exit code 1 if anything is broken.
"""

import os
import re
import sys
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "build", "__pycache__", ".cache", "node_modules"}

INLINE = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
REFDEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+\"[^\"]*\")?\s*$")
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s{0,3}(```|~~~)")


def md_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(".md"):
                yield os.path.join(dirpath, name)


def prose_lines(path):
    """(line number, text) for lines outside fenced code, inline code blanked."""
    in_fence = False
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if not in_fence:
                yield n, re.sub(r"`[^`]*`", lambda m: " " * len(m.group()), line)


def slug(text):
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # [text](url) -> text
    text = re.sub(r"<[^>]+>", "", text)                     # inline HTML
    text = text.replace("`", "").replace("*", "")
    text = re.sub(r"(?<!\w)_|_(?!\w)", "", text)             # _emphasis_, keep snake_case
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


_anchor_cache = {}


def anchors(path):
    if path not in _anchor_cache:
        seen = {}
        result = set()
        in_fence = False
        with open(path, encoding="utf-8") as f:
            for line in f:
                if FENCE.match(line):
                    in_fence = not in_fence
                    continue
                m = None if in_fence else HEADING.match(line)
                if m:
                    base = slug(m.group(2))
                    k = seen.get(base, 0)
                    seen[base] = k + 1
                    result.add(base if k == 0 else f"{base}-{k}")
                for a in re.findall(r"<a\s+(?:name|id)=\"([^\"]+)\"", line):
                    result.add(a)
        _anchor_cache[path] = result
    return _anchor_cache[path]


def check(path):
    errors = []
    for n, line in prose_lines(path):
        targets = INLINE.findall(line)
        m = REFDEF.match(line)
        if m:
            targets.append(m.group(1))
        for target in targets:
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
                continue  # http:, https:, mailto:
            file_part, _, anchor = target.partition("#")
            file_part = unquote(file_part)
            dest = os.path.normpath(os.path.join(os.path.dirname(path), file_part)) if file_part else path
            where = f"{os.path.relpath(path, ROOT)}:{n}"
            if not os.path.exists(dest):
                errors.append(f"{where}: missing {target}")
                continue
            if not os.path.realpath(dest).startswith(ROOT + os.sep):
                errors.append(f"{where}: points outside the repository: {target}")
                continue
            if anchor and dest.endswith(".md") and unquote(anchor).lower() not in anchors(dest):
                errors.append(f"{where}: no heading #{anchor} in {os.path.relpath(dest, ROOT)}")
    return errors


def main():
    errors = []
    count = 0
    for path in md_files():
        count += 1
        errors += check(path)
    for e in errors:
        print(e)
    print(f"{count} files checked, {len(errors)} broken links")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
