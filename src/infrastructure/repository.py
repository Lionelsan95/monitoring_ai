"""
Infrastructure SQLite — MetricRecord repository.

Single responsibility: read and write MetricRecord to the database.
Implicitly implements RepositoryPort via duck typing / Protocol.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from config import DBConfig
from domain.schemas import MetricRecord

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS metric_records (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT    NOT NULL,
    payload   TEXT    NOT NULL
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_timestamp ON metric_records (timestamp);
"""


class MetricRepository:
    """
    SQLite access for MetricRecord.
    Instantiate once per process; safe for concurrent reads.
    """

    def __init__(self, config: DBConfig) -> None:
        self._path = config.path
        self._init_db()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)
            conn.execute(_CREATE_INDEX)
            conn.commit()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, record: MetricRecord) -> None:
        """Persist a MetricRecord. The JSON payload is the full model."""
        ts      = record.timestamp.astimezone(timezone.utc).isoformat()
        payload = record.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO metric_records (timestamp, payload) VALUES (?, ?)",
                (ts, payload),
            )
            conn.commit()

    def save_batch(self, records: list[MetricRecord]) -> int:
        """Persist a list of records in a single transaction. Returns the number inserted."""
        rows = [
            (r.timestamp.astimezone(timezone.utc).isoformat(), r.model_dump_json())
            for r in records
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO metric_records (timestamp, payload) VALUES (?, ?)",
                rows,
            )
            conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def fetch_range(self, start: datetime, end: datetime) -> list[MetricRecord]:
        """Return all records whose timestamp falls within [start, end]."""
        start_iso = start.astimezone(timezone.utc).isoformat()
        end_iso   = end.astimezone(timezone.utc).isoformat()

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM metric_records
                WHERE  timestamp >= ? AND timestamp <= ?
                ORDER  BY timestamp ASC
                """,
                (start_iso, end_iso),
            ).fetchall()

        return [MetricRecord.model_validate_json(row["payload"]) for row in rows]

    def count(self) -> int:
        """Return the total number of records in the database."""
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM metric_records").fetchone()[0]
