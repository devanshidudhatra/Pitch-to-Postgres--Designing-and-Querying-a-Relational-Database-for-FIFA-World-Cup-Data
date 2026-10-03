"""
Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
Create the LOCAL test database named in .env (DB_NAME) if it does not exist yet.

Safety: refuses to run unless DB_HOST is localhost / 127.0.0.1 / ::1.
On the course server the database is provided by the instructor; do not use this script there.

Usage:  python src/create_local_db.py
"""

import sys
from pathlib import Path

from sqlalchemy import URL, create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import load_settings  # noqa: E402

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def main() -> int:
    s = load_settings()
    if s["DB_HOST"] not in LOCAL_HOSTS:
        print(f"Refusing: DB_HOST is {s['DB_HOST']}, not a local host. This script is for the local test database only.")
        return 1
    # connect to the default maintenance database to create the project database
    url = URL.create("postgresql+psycopg2", username=s["DB_USER"], password=s["DB_PASSWORD"],
                     host=s["DB_HOST"], port=int(s["DB_PORT"]), database="postgres")
    engine = create_engine(url, isolation_level="AUTOCOMMIT")  # CREATE DATABASE cannot run in a transaction
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": s["DB_NAME"]}).scalar()
        if exists:
            print(f"Database '{s['DB_NAME']}' already exists on {s['DB_HOST']}.")
        else:
            name = s["DB_NAME"].replace('"', '""')
            conn.execute(text(f'CREATE DATABASE "{name}" ENCODING \'UTF8\' TEMPLATE template0'))
            print(f"Created database '{s['DB_NAME']}' on {s['DB_HOST']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
