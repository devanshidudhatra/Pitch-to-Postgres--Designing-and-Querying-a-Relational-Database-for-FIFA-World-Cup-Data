"""
Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
Connection check. This script is read-only: it creates, changes and deletes nothing.

Usage:  python src/check_connection.py
"""

import sys

from sqlalchemy import text

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from db import describe, get_engine  # noqa: E402

CHECKS = {
    "server version": "SELECT version()",
    "connected as": "SELECT current_user",
    "database": "SELECT current_database()",
    "search_path": "SHOW search_path",
    "default schema": "SELECT current_schema()",
    "can create tables in that schema": "SELECT has_schema_privilege(current_schema(), 'CREATE')",
    "World Cup tables already present": """
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name IN ('tournaments','teams','players','matches','goals','squads')""",
}


def main() -> int:
    try:
        print("Target:", describe())
        engine = get_engine()
        with engine.connect() as conn:
            for label, sql in CHECKS.items():
                print(f"  {label:34s} {conn.execute(text(sql)).scalar()}")
    except Exception as exc:  # show the reason, never the password
        print("Connection FAILED:", type(exc).__name__, str(exc).splitlines()[0])
        print("Check: on the university network / VPN? Values in .env correct? Server reachable on DB_PORT?")
        return 1
    print("Connection OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
