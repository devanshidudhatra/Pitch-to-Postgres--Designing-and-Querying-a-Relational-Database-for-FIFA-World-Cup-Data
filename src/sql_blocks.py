"""
Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
Split sql/queries.sql (or sql/views.sql) into documented blocks.

Each block starts with a comment header:
    -- Qnn. Title                      (or: -- Vn. Title for views)
    -- Business question: ...         (may continue on following comment lines)
    -- SQL concepts: ...
    -- Expected result: ...
followed by one SQL statement ending with ';'.
"""

from __future__ import annotations

import re
from pathlib import Path

HEADER = re.compile(r"^-- ([QV]\d+)\. (.+)$")
FIELDS = {"Business question:": "question", "SQL concepts:": "concepts", "Expected result:": "expected",
          "Purpose:": "question", "Based on:": "based_on"}


def parse(path: Path) -> list[dict]:
    blocks, cur, field = [], None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = HEADER.match(line)
        if m:
            cur = {"id": m.group(1), "title": m.group(2).strip(), "question": "", "concepts": "",
                   "expected": "", "based_on": "", "sql": []}
            blocks.append(cur)
            field = None
            continue
        if cur is None:
            continue
        if line.startswith("-- ="):
            field = None
            continue
        if line.startswith("--") and not cur["sql"]:
            text = line[2:].strip()
            for label, key in FIELDS.items():
                if text.startswith(label):
                    field = key
                    cur[key] = text[len(label):].strip()
                    break
            else:
                if field and text:
                    cur[field] += " " + text
            continue
        if line.strip() or cur["sql"]:
            cur["sql"].append(line)
    for b in blocks:
        b["sql"] = "\n".join(b["sql"]).strip()
        assert b["sql"].endswith(";"), f"{b['id']} does not end with ';'"
    return blocks
