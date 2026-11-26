"""Conservatively baseline an existing, fully matching RetailAI demo schema.

Only needed if an existing SQLite installation intends to use Alembic for
future schema updates. Creates the Alembic revision marker but NO app tables,
no demo records, and no synthetic seeds. Requires explicit --confirm.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from app.db import Base, make_engine
import app.models  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent


def stamp_existing(url: str, *, confirm: bool = False) -> None:
    if not confirm:
        raise ValueError("Refusing to stamp without --confirm; back up the DB first")
    if not url.startswith("sqlite:///"):
        raise ValueError("This convenience script only supports an existing SQLite demo database")
    # A non-existent SQLite file could be silently created by SQLAlchemy.
    database_path = url[len("sqlite:///"):]
    if database_path == ":memory:" or not Path(database_path).exists():
        raise ValueError("Database file does not already exist; use alembic upgrade head for new DBs")
    engine = make_engine(url)
    try:
        inspector = inspect(engine)
        actual_tables = set(inspector.get_table_names())
        if "alembic_version" in actual_tables:
            raise ValueError("Database already has Alembic versioning; use alembic current")
        required = set(Base.metadata.tables)
        if not required.issubset(actual_tables):
            raise ValueError("Database is missing required RetailAI tables; refusing to stamp")
        for name, table in Base.metadata.tables.items():
            actual_columns = {column["name"] for column in inspector.get_columns(name)}
            expected_columns = set(table.columns.keys())
            if expected_columns != actual_columns:
                raise ValueError(f"Database table {name} has a different column layout; refusing to stamp")
            expected_indexes = {index.name for index in table.indexes}
            actual_indexes = {index["name"] for index in inspector.get_indexes(name)}
            if not expected_indexes.issubset(actual_indexes):
                raise ValueError(f"Database table {name} is missing expected indexes; refusing to stamp")
            expected_unique = {c.name for c in table.constraints
                               if getattr(c, "__visit_name__", "") == "unique_constraint"}
            actual_unique = {c["name"] for c in inspector.get_unique_constraints(name)}
            if not expected_unique.issubset(actual_unique):
                raise ValueError(f"Database table {name} is missing unique constraints; refusing to stamp")
    finally:
        engine.dispose()
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.stamp(Config(str(ROOT / "alembic.ini")), "head")
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url
    print("RetailAI existing SQLite baseline: PASS (stamp only, no schema or row changes)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="Confirm the DB backup and baseline")
    args = parser.parse_args()
    stamp_existing(os.getenv("DATABASE_URL", "sqlite:///./retailai_demo.db"), confirm=args.confirm)
