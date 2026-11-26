"""Reproducible, offline Alembic smoke test on a disposable SQLite database."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from app.core.db import Base, make_engine
import app.models  # noqa: F401 - populate Base.metadata

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"


def check_migrations() -> None:
    with tempfile.TemporaryDirectory(prefix="retailai_alembic_") as temp:
        url = "sqlite:///" + (Path(temp) / "schema.db").as_posix()
        old_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = url
        try:
            config = Config(str(PROJECT_ROOT / "alembic.ini"))
            command.upgrade(config, "head")
            engine = make_engine(url)
            try:
                inspector = inspect(engine)
                expected = set(Base.metadata.tables)
                actual = set(inspector.get_table_names())
                assert expected.issubset(actual), f"Missing tables: {expected - actual}"
                for table_name, table in Base.metadata.tables.items():
                    expected_columns = set(table.columns.keys())
                    actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
                    assert actual_columns == expected_columns, table_name
                assert "alembic_version" in actual
                with engine.connect() as conn:
                    revision = conn.scalar(text("SELECT version_num FROM alembic_version"))
                assert revision == "05aed75aedb3", f"Unexpected revision: {revision}"
            finally:
                engine.dispose()
        finally:
            if old_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old_url
    print("RetailAI Alembic migration smoke: PASS")
    print("Initial schema, all SQLAlchemy tables/columns, and revision: PASS")
    print("Disposable SQLite only: no local application DB or AWS calls")


if __name__ == "__main__":
    check_migrations()
