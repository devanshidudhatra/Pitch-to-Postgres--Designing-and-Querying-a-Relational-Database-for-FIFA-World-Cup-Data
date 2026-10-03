"""
Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
Run sql/ddl.sql (or another SQL file) against the database configured in .env.

Usage:
    python src/apply_ddl.py                    create tables (safe to rerun; no DROP)
    python src/apply_ddl.py --reset-local      LOCAL ONLY: drop everything first (sql/reset_local.sql)
    python src/apply_ddl.py sql/views.sql      run another SQL file
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import ROOT, describe, get_engine, load_settings  # noqa: E402

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def run_sql_file(engine, path: Path) -> None:
    """Run a whole SQL file in one transaction. psycopg2 accepts several statements in one call."""
    sql = path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)


def is_local() -> bool:
    return load_settings()["DB_HOST"] in LOCAL_HOSTS


def main(argv: list[str]) -> int:
    reset = "--reset-local" in argv
    files = [Path(a) for a in argv if not a.startswith("--")] or [ROOT / "sql" / "ddl.sql"]
    print("Target:", describe())
    engine = get_engine()
    if reset:
        if not is_local():
            print("Refusing --reset-local: DB_HOST is not local. Destructive statements are not allowed on the course server.")
            return 1
        run_sql_file(engine, ROOT / "sql" / "reset_local.sql")
        print("Local database reset (all project tables and views dropped).")
    for f in files:
        f = f if f.is_absolute() else ROOT / f
        run_sql_file(engine, f)
        print(f"Executed {f.relative_to(ROOT)}")
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM information_schema.tables "
                              "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'")).scalar()
    print(f"Base tables in schema now: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
