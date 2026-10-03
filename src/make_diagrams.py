"""
Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
Generate the ER diagram and relational schema diagrams (crow's foot notation) as PNG files in diagrams/.

The diagrams are built from the LIVE database catalog (tables, columns, keys, foreign keys), and the
cardinalities are measured on the loaded data, so they always match sql/ddl.sql.
Rendering: Mermaid erDiagram -> headless Chrome/Edge -> PNG (whitespace trimmed with Pillow).
mermaid.js is loaded from cdn.jsdelivr.net, so an internet connection is needed.

Usage:  python src/make_diagrams.py        (needs the tables created and loaded, e.g. on the local database)
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import ROOT, get_engine  # noqa: E402
from md_to_pdf import find_browser  # noqa: E402

OUT = ROOT / "diagrams"

FK_SQL = """
SELECT c.conname AS name, cl.relname AS child, pl.relname AS parent,
       array_agg(a.attname ORDER BY k.ord) AS child_cols,
       array_agg(pa.attname ORDER BY k.ord) AS parent_cols,
       bool_and(a.attnotnull) AS not_null
FROM pg_constraint c
JOIN pg_class cl ON cl.oid = c.conrelid
JOIN pg_class pl ON pl.oid = c.confrelid
JOIN pg_namespace n ON n.oid = cl.relnamespace
CROSS JOIN LATERAL unnest(c.conkey, c.confkey) WITH ORDINALITY AS k(ck, pk, ord)
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.ck
JOIN pg_attribute pa ON pa.attrelid = c.confrelid AND pa.attnum = k.pk
WHERE c.contype = 'f' AND n.nspname = current_schema()
GROUP BY c.conname, cl.relname, pl.relname
ORDER BY child, parent, name
"""

COL_SQL = """
SELECT c.table_name, c.column_name, c.data_type, c.is_nullable, c.ordinal_position
FROM information_schema.columns c
JOIN information_schema.tables t ON t.table_name = c.table_name AND t.table_schema = c.table_schema
WHERE c.table_schema = current_schema() AND t.table_type = 'BASE TABLE'
ORDER BY c.table_name, c.ordinal_position
"""

KEY_SQL = """
SELECT tc.table_name, kcu.column_name, tc.constraint_type, tc.constraint_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
WHERE tc.table_schema = current_schema() AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
"""

TYPE_SHORT = {"character varying": "varchar", "character": "char", "smallint": "smallint", "integer": "int",
              "boolean": "bool", "date": "date", "time without time zone": "time"}

# Diagram subsets: (file stem, title, main tables shown with all columns, context tables shown with keys only)
SUBSETS = [
    ("schema_1_reference_structure", "Relational schema 1/5: reference data, people and tournament structure",
     ["teams", "confederations", "referees", "tournaments", "tournament_stages", "groups",
      "players", "managers", "stadiums", "awards", "positions"], []),
    ("schema_2_participation", "Relational schema 2/5: participation and standings",
     ["qualified_teams", "host_countries", "tournament_standings", "group_standings", "squads",
      "manager_appointments", "referee_appointments"],
     ["tournaments", "teams", "players", "managers", "referees", "groups", "positions"]),
    ("schema_3_matches", "Relational schema 3/5: matches, team, referee and manager appearances",
     ["matches", "team_appearances", "referee_appearances", "manager_appearances"],
     ["tournament_stages", "groups", "stadiums", "qualified_teams", "referee_appointments", "manager_appointments"]),
    ("schema_4_goals_cards_shootouts", "Relational schema 4/5: goals, cards and shoot-out kicks",
     ["goals", "bookings", "penalty_kicks"],
     ["matches", "team_appearances", "squads"]),
    ("schema_5_lineups_subs_awards", "Relational schema 5/5: line-ups, substitutions and awards",
     ["player_appearances", "substitutions", "award_winners"],
     ["matches", "team_appearances", "squads", "positions", "awards"]),
]

# Conceptual ER diagram, split into two sheets for readability (shared entities appear on both).
ER_SUBSETS = [
    ("er_diagram_1_tournaments_people", "ER diagram 1/2: tournaments, teams, people and awards",
     ["confederations", "teams", "tournaments", "tournament_stages", "groups", "group_standings", "qualified_teams",
      "host_countries", "tournament_standings", "squads", "players", "positions", "managers", "manager_appointments",
      "referees", "referee_appointments", "awards", "award_winners"]),
    ("er_diagram_2_matches_events", "ER diagram 2/2: matches and match events",
     ["tournament_stages", "groups", "stadiums", "qualified_teams", "matches", "team_appearances", "referee_appointments",
      "referee_appearances", "manager_appointments", "manager_appearances", "squads", "positions", "player_appearances",
      "goals", "bookings", "substitutions", "penalty_kicks"]),
]

# For the conceptual ER diagram: relationship verbs, and the FKs left out because they only repeat
# a path already drawn (they enforce consistency of the redundant tournament_id / second team column).
VERBS = {
    ("teams", "confederations"): "belongs to", ("referees", "confederations"): "belongs to",
    ("tournament_stages", "tournaments"): "has stage", ("groups", "tournament_stages"): "has group",
    ("qualified_teams", "tournaments"): "includes", ("qualified_teams", "teams"): "takes part",
    ("host_countries", "qualified_teams"): "hosts", ("tournament_standings", "qualified_teams"): "finishes top 4",
    ("group_standings", "groups"): "ranks", ("group_standings", "qualified_teams"): "placed",
    ("squads", "qualified_teams"): "registers", ("squads", "players"): "listed in", ("squads", "positions"): "position",
    ("manager_appointments", "qualified_teams"): "led by", ("manager_appointments", "managers"): "appointed",
    ("referee_appointments", "tournaments"): "appoints", ("referee_appointments", "referees"): "appointed",
    ("matches", "tournament_stages"): "contains", ("matches", "groups"): "group match", ("matches", "stadiums"): "hosts",
    ("matches", "qualified_teams"): "plays", ("team_appearances", "matches"): "has two sides",
    ("team_appearances", "qualified_teams"): "plays", ("team_appearances", "team_appearances"): "opponent",
    ("referee_appearances", "matches"): "officiated", ("referee_appearances", "referee_appointments"): "referees",
    ("manager_appearances", "team_appearances"): "managed", ("manager_appearances", "manager_appointments"): "manages",
    ("player_appearances", "team_appearances"): "lines up", ("player_appearances", "squads"): "plays",
    ("player_appearances", "positions"): "position", ("goals", "team_appearances"): "scored in",
    ("goals", "squads"): "scores", ("bookings", "team_appearances"): "booked in", ("bookings", "squads"): "booked",
    ("substitutions", "team_appearances"): "made in", ("substitutions", "squads"): "subbed",
    ("penalty_kicks", "team_appearances"): "shoot-out", ("penalty_kicks", "squads"): "takes kick",
    ("award_winners", "awards"): "given", ("award_winners", "squads"): "wins",
}


def load_catalog(engine):
    with engine.connect() as c:
        fks = [dict(r._mapping) for r in c.execute(text(FK_SQL))]
        cols = [dict(r._mapping) for r in c.execute(text(COL_SQL))]
        keys = [dict(r._mapping) for r in c.execute(text(KEY_SQL))]
        for fk in fks:   # measure cardinality on the data
            cc, pc = fk["child_cols"], fk["parent_cols"]
            notnull = " AND ".join(f"{x} IS NOT NULL" for x in cc)
            fk["max_children"] = c.execute(text(
                f"SELECT COALESCE(max(n), 0) FROM (SELECT count(*) AS n FROM {fk['child']} WHERE {notnull} "
                f"GROUP BY {', '.join(cc)}) s")).scalar()
            cond = " AND ".join(f"ch.{a} = p.{b}" for a, b in zip(cc, pc))
            fk["parents_without_child"] = c.execute(text(
                f"SELECT count(*) FROM (SELECT DISTINCT {', '.join(pc)} FROM {fk['parent']}) p "
                f"WHERE NOT EXISTS (SELECT 1 FROM {fk['child']} ch WHERE {cond})")).scalar()
    pk, uk = {}, {}
    ucount = {}
    for k in keys:
        ucount[k["constraint_name"]] = ucount.get(k["constraint_name"], 0) + 1
    for k in keys:
        if k["constraint_type"] == "PRIMARY KEY":
            pk.setdefault(k["table_name"], set()).add(k["column_name"])
        elif ucount[k["constraint_name"]] == 1:      # mark UK only for single-column UNIQUE constraints
            uk.setdefault(k["table_name"], set()).add(k["column_name"])
    tables = {}
    for col in cols:
        tables.setdefault(col["table_name"], []).append(col)
    return tables, pk, uk, fks


def crow(fk) -> str:
    """Mermaid crow's foot: parent side | child side."""
    left = "||" if fk["not_null"] else "|o"
    optional = fk["parents_without_child"] > 0
    if fk["max_children"] <= 1:
        right = "o|" if optional else "||"
    else:
        right = "o{" if optional else "|{"
    return f"{left}--{right}"


def entity_block(name, cols, pk, uk, fkcols, keys_only=False, referenced=frozenset()) -> str:
    lines = [f"  {name.upper()} {{"]
    for c in cols:
        n = c["column_name"]
        if keys_only and n not in pk.get(name, set()) and n not in referenced:
            continue
        marks = [m for m, cond in (("PK", n in pk.get(name, set())), ("FK", n in fkcols.get(name, set())),
                                   ("UK", n in uk.get(name, set()) and n not in pk.get(name, set()))) if cond]
        t = TYPE_SHORT.get(c["data_type"], c["data_type"].split()[0])
        null = "" if c["is_nullable"] == "NO" else ' "nullable"'
        lines.append(f"    {t} {n} {', '.join(marks)}{null}".rstrip())
    lines.append("  }")
    return "\n".join(lines)


def relational_mermaid(tables, pk, uk, fks, main, context) -> str:
    shown = set(main) | set(context)
    fkcols = {}
    for fk in fks:
        fkcols.setdefault(fk["child"], set()).update(fk["child_cols"])
    out = ["erDiagram"]
    for t in main:
        out.append(entity_block(t, tables[t], pk, uk, fkcols))
    for t in context:   # context tables: primary key plus the columns referenced from this sheet
        ref = {c for fk in fks if fk["parent"] == t and fk["child"] in main for c in fk["parent_cols"]}
        out.append(entity_block(t, tables[t], pk, uk, fkcols, keys_only=True, referenced=ref))
    for fk in fks:
        if fk["child"] in shown and fk["parent"] in shown and (fk["child"] in main or fk["parent"] in main):
            out.append(f'  {fk["parent"].upper()} {crow(fk)} {fk["child"].upper()} : "{", ".join(fk["child_cols"])}"')
    return "\n".join(out)


def er_mermaid(tables, fks, keep) -> str:
    out = ["erDiagram"]
    seen = set()
    for fk in fks:
        key = (fk["child"], fk["parent"])
        if key not in VERBS or key in seen or fk["child"] not in keep or fk["parent"] not in keep:
            continue   # skip consistency-only FKs and second FKs between the same pair
        seen.add(key)
        out.append(f'  {fk["parent"].upper()} {crow(fk)} {fk["child"].upper()} : "{VERBS[key]}"')
    drawn = {x for k in seen for x in k}
    for t in sorted(set(keep) - drawn):
        out.append(f"  {t.upper()}")
    return "\n".join(out)


HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>body{{margin:0;padding:24px;background:#fff;font-family:Arial,sans-serif}}
h1{{font-size:22px;color:#0b3d2e;margin:0 0 4px}} p{{margin:0 0 14px;font-size:13px;color:#444}}</style></head>
<body><h1>{title}</h1><p>{sub}</p><pre class="mermaid">{code}</pre>
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
mermaid.initialize({{ startOnLoad:false, theme:"neutral", er:{{ useMaxWidth:false, layoutDirection:"{direction}",
  entityPadding:12, fontSize:14, minEntityWidth:90 }} }});
await mermaid.run({{ querySelector:"pre.mermaid" }});
const s=document.querySelector("svg"); const b=s.getBoundingClientRect();
document.title = "SIZE:" + Math.ceil(b.right) + "x" + Math.ceil(b.bottom);
</script></body></html>"""

SUB = ("Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data | crow's foot notation, "
       "cardinalities measured on the loaded data | tables from other sheets show key columns only | "
       "data: Fjelstul World Cup Database (CC-BY-SA 4.0)")


def render(code: str, title: str, stem: str, direction: str = "TB") -> Path:
    browser = find_browser()
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / f"{stem}.html"
        sub = SUB.replace(" | tables from other sheets show key columns only", "") if stem.startswith("er_") else SUB
        html.write_text(HTML.format(title=title, sub=sub, code=code, direction=direction), encoding="utf-8")
        base = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--virtual-time-budget=30000"]
        dom = subprocess.run(base + ["--window-size=8000,8000", "--dump-dom", html.as_uri()],
                             capture_output=True, text=True, encoding="utf-8", timeout=180).stdout
        m = re.search(r"SIZE:(\d+)x(\d+)", dom)
        if not m:
            raise SystemExit(f"Mermaid did not render {stem} (internet connection needed for mermaid.js).")
        w, h = int(m.group(1)) + 60, int(m.group(2)) + 60
        png = OUT / f"{stem}.png"
        subprocess.run(base + [f"--window-size={w},{h}", "--force-device-scale-factor=2",
                               f"--screenshot={png}", html.as_uri()], capture_output=True, timeout=180, check=True)
    img = Image.open(png).convert("RGB")
    bbox = ImageChops.difference(img, Image.new("RGB", img.size, "white")).getbbox()
    if bbox:
        img = img.crop((max(bbox[0] - 30, 0), max(bbox[1] - 30, 0), min(bbox[2] + 30, img.width), min(bbox[3] + 30, img.height)))
    img.save(png, optimize=True)
    (OUT / f"{stem}.mmd").write_text(code, encoding="utf-8")   # keep the Mermaid source too
    return png


def main() -> int:
    OUT.mkdir(exist_ok=True)
    engine = get_engine()
    tables, pk, uk, fks = load_catalog(engine)
    print(f"Catalog: {len(tables)} tables, {len(fks)} foreign keys")
    outputs = [render(er_mermaid(tables, fks, keep), title, stem, "LR") for stem, title, keep in ER_SUBSETS]
    for stem, title, main, context in SUBSETS:
        outputs.append(render(relational_mermaid(tables, pk, uk, fks, main, context), title, stem, "LR"))
    for p in outputs:
        im = Image.open(p)
        print(f"Wrote {p.relative_to(ROOT)} ({im.width}x{im.height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
