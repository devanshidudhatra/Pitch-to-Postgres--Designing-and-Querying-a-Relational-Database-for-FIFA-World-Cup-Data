"""
Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
Shared database connection helper.

All notebooks and scripts get their SQLAlchemy engine from here, so switching between the
local test database and the course server only needs a change to the .env file.

Settings (read from .env in the project root, or from environment variables):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD   required
    DB_SCHEMA                                          optional; sets the search_path
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]


def load_settings() -> dict[str, str]:
    """Load .env (environment variables already set take priority) and return the settings."""
    load_dotenv(ROOT / ".env", override=False)
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
        raise RuntimeError(
            f"Missing database settings: {', '.join(missing)}. "
            "Copy .env.example to .env and fill in the values."
        )
    return {k: os.getenv(k, "") for k in REQUIRED + ["DB_SCHEMA"]}


def get_engine() -> Engine:
    """Build a SQLAlchemy engine for PostgreSQL from the settings. The password is never printed."""
    s = load_settings()
    url = URL.create(
        "postgresql+psycopg2",
        username=s["DB_USER"],
        password=s["DB_PASSWORD"],   # URL.create escapes special characters safely
        host=s["DB_HOST"],
        port=int(s["DB_PORT"]),
        database=s["DB_NAME"],
    )
    connect_args = {"connect_timeout": 10}
    if s["DB_SCHEMA"]:
        connect_args["options"] = f"-csearch_path={s['DB_SCHEMA']}"
    return create_engine(url, connect_args=connect_args)


def describe() -> str:
    """Safe, password-free description of the target database, for printing in notebooks."""
    s = load_settings()
    schema = s["DB_SCHEMA"] or "(default search_path)"
    return f"{s['DB_USER']}@{s['DB_HOST']}:{s['DB_PORT']}/{s['DB_NAME']}  schema: {schema}"
