"""
Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
Build docs/final_report.md and docs/final_report.pdf.

docs/final_report_src.md holds the narrative. This script
  * replaces '<!-- generated: queries -->' with every query of sql/queries.sql (question, concepts,
    SQL, first 10 result rows from the live database, interpretation from src/report_content.py),
  * replaces '<!-- generated: views -->' with sample rows from each view,
  * expands '<!-- include: ... -->' directives (other documents, sql/ddl.sql, sql/views.sql),
and writes the complete Markdown plus the PDF. It needs the database in .env to be loaded and to have
the views (run notebooks 03 and 05 first). It only reads from the database.

Usage:  python src/build_final_report.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402
import sql_blocks  # noqa: E402
from md_to_pdf import convert, expand_includes  # noqa: E402
from report_content import INTERP  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

THEMES = [
    ("6.1 Team performance", ["Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07", "Q08", "Q09"]),
    ("6.2 Player performance", ["Q10", "Q11", "Q12", "Q13", "Q14", "Q15", "Q16"]),
    ("6.3 Goals and scoring patterns", ["Q17", "Q18", "Q19", "Q20", "Q21"]),
    ("6.4 Discipline and refereeing (1970 onwards)", ["Q22", "Q23", "Q24", "Q25"]),
    ("6.5 Venues and hosting", ["Q26"]),
    ("6.6 Managers", ["Q27", "Q28"]),
    ("6.7 Awards", ["Q29"]),
    ("6.8 Data quality and integrity", ["Q30"]),
]

VIEW_SAMPLES = [
    ("v_match_results", "Latest five matches",
     "SELECT year, stage_name, home_team, score, away_team, result, winner_incl_shootout, went_to "
     "FROM v_match_results ORDER BY match_date DESC, match_id DESC LIMIT 5"),
    ("v_top_scorers", "Top of the all-time ranking",
     "SELECT goal_rank, player, teams, goals, penalty_goals, tournaments_scored_in "
     "FROM v_top_scorers ORDER BY goal_rank, player LIMIT 5"),
    ("v_tournament_summary", "Five most recent tournaments",
     "SELECT year, hosts, champion, runner_up, teams, matches, goals_per_match, top_scorers, top_scorer_goals, cards_per_match "
     "FROM v_tournament_summary ORDER BY year DESC LIMIT 5"),
    ("v_team_performance", "Most successful teams",
     "SELECT team_name, tournaments, matches, won, drawn, lost, win_pct, titles, finals, best_finish "
     "FROM v_team_performance ORDER BY titles DESC, win_pct DESC LIMIT 5"),
    ("v_referee_discipline", "Strictest referees with at least five matches since 1970",
     "SELECT referee, country, matches_since_1970, cards, sendings_off, cards_per_match "
     "FROM v_referee_discipline WHERE matches_since_1970 >= 5 ORDER BY cards_per_match DESC, referee LIMIT 5"),
    ("v_host_performance", "Five most recent hosts",
     "SELECT year, host, matches, won, drawn, lost, stage_reached, finish "
     "FROM v_host_performance ORDER BY year DESC, host LIMIT 5"),
    ("v_head_to_head", "England against West Germany and Germany",
     "SELECT team, opponent, matches, wins, draws, losses, goals_for, goals_against, first_meeting, last_meeting "
     "FROM v_head_to_head WHERE team = 'England' AND opponent IN ('West Germany', 'Germany') ORDER BY opponent"),
]


XREFS = [   # cross-references inside the included Milestone 2 text -> places in this report
    ("(reproduced in full in Section 7)", "(reproduced in full in Appendix A)"),
    ("rejected by the intended constraint (Section 6)", "rejected by the intended constraint (listed in the Milestone 2 report, Section 6)"),
    ("from the columns we keep (Section 3.2)", "from the columns we keep (Section 4.2, 'What was removed')"),
    ("controlled exception (Section 3.5)", "controlled exception (Section 4.2, 'Controlled redundancy')"),
    ("is replaced by `stage_number` (Section 3.6)", "is replaced by `stage_number` (Section 4.2, 'Stages and groups')"),
    ("does not store (Milestone 2, Section 3.2)", "does not store (Section 4.2, 'What was removed')"),
]


def md_table(df: pd.DataFrame, max_chars: int = 70) -> str:
    def cell(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        s = str(v)
        s = s.replace("|", "\\|").replace("\n", " ")
        return s if len(s) <= max_chars else s[: max_chars - 3] + "..."
    head = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = ["| " + " | ".join(cell(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([head, sep] + rows)


def queries_section(engine) -> str:
    blocks = {b["id"]: b for b in sql_blocks.parse(ROOT / "sql" / "queries.sql")}
    out = []
    for theme, ids in THEMES:
        out.append(f"### {theme}\n")
        for qid in ids:
            b = blocks[qid]
            df = pd.read_sql_query(b["sql"], engine)
            out.append(f"#### {qid}. {b['title']}\n")
            out.append(f"**Business question:** {b['question']}\n")
            out.append(f"**SQL concepts:** {b['concepts']}\n")
            out.append(f"**Expected result:** {b['expected']}\n")
            out.append("```sql\n" + b["sql"] + "\n```\n")
            more = f" (first 10 of {len(df)} rows)" if len(df) > 10 else f" ({len(df)} rows)"
            out.append(f"*Result{more}:*\n")
            out.append(md_table(df.head(10)) + "\n")
            out.append(f"**Interpretation.** {INTERP[qid]}\n")
    return "\n".join(out)


def views_section(engine) -> str:
    out = []
    for name, title, sql in VIEW_SAMPLES:
        df = pd.read_sql_query(sql, engine)
        out.append(f"**`{name}`: {title}**\n")
        out.append(f"`{sql}`\n")
        out.append(md_table(df) + "\n")
    return "\n".join(out)


def main() -> int:
    engine = db.get_engine()
    print("Reading results from:", db.describe())
    src = (DOCS / "final_report_src.md").read_text(encoding="utf-8")
    src = src.replace("<!-- generated: queries -->", queries_section(engine))
    src = src.replace("<!-- generated: views -->", views_section(engine))
    full = expand_includes(src, DOCS)
    # Included documents keep their own numbering; drop numbers from included sub-headings (level 4+)
    # and point their cross-references at the right place in this report.
    full = re.sub(r"^(#{4,}) \d+(?:\.\d+)*\.? ", r"\1 ", full, flags=re.M)
    for old, new in XREFS:
        assert old in full, f"cross-reference not found: {old}"
        full = full.replace(old, new)
    header = ("<!-- Generated by src/build_final_report.py from docs/final_report_src.md; "
              "edit the source, not this file. -->\n")
    out = DOCS / "final_report.md"
    out.write_text(header + full, encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)}")
    pdf = convert(out)
    print(f"Wrote {pdf.relative_to(ROOT)} ({pdf.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
