"""
Storage backends for MQTT messages.

Architecture:
    StorageBackend (ABC)
        ├── FileLogger     — appends timestamped .txt files per session
        └── DatabaseLogger — stub for future PostgreSQL integration

Usage:
    logger = FileLogger(directory="logs")
    logger.store_message(mqtt_msg)
    logger.close()
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mqtt_client import MqttMessage


class StorageBackend(ABC):
    """Abstract base for all message storage implementations."""

    @abstractmethod
    def store_message(self, msg: "MqttMessage") -> None:
        """Persist a single MQTT message."""

    @abstractmethod
    def close(self) -> None:
        """Flush and release any held resources."""

    @property
    @abstractmethod
    def info(self) -> str:
        """Short human-readable description (shown in status bar)."""


# ---------------------------------------------------------------------------
# File-based backend
# ---------------------------------------------------------------------------

class FileLogger(StorageBackend):
    """
    Appends every received message to a plain-text log file.

    *filename* behaviour:
    - Omitted / empty string → auto-name: ``<directory>/mqtt_<YYYYMMDD_HHMMSS>.txt``
    - Relative path          → placed inside *directory*
    - Absolute path          → used as-is (*directory* is ignored)

    Each line has the format:
        <ISO timestamp>  <QoS>  <R?>  <topic>  <payload>
    """

    def __init__(
        self,
        directory: str | os.PathLike = "logs",
        filename: str | os.PathLike = "",
    ) -> None:
        filename = str(filename).strip()

        if filename and Path(filename).is_absolute():
            self._path = Path(filename)
            self._path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self._dir = Path(directory)
            self._dir.mkdir(parents=True, exist_ok=True)
            if filename:
                self._path = self._dir / filename
            else:
                session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                self._path = self._dir / f"mqtt_{session_ts}.txt"

        self._file = self._path.open("a", encoding="utf-8", buffering=1)  # line-buffered

        # Write a header so the file is self-describing.
        self._file.write(
            f"# MQTT Monitor log — session started {datetime.now().isoformat()}\n"
            "# Columns: timestamp | QoS | Retain | topic | payload\n\n"
        )

    def store_message(self, msg: "MqttMessage") -> None:
        retain_flag = "R" if msg.retain else " "
        line = (
            f"{msg.timestamp.isoformat(timespec='milliseconds')}  "
            f"QoS={msg.qos}  {retain_flag}  "
            f"{msg.topic}  {msg.payload}\n"
        )
        self._file.write(line)

    def close(self) -> None:
        if not self._file.closed:
            self._file.write(f"\n# Session ended {datetime.now().isoformat()}\n")
            self._file.flush()
            self._file.close()

    @property
    def info(self) -> str:
        return str(self._path)


# ---------------------------------------------------------------------------
# Database stub
# ---------------------------------------------------------------------------

class DatabaseLogger(StorageBackend):
    """
    PostgreSQL-backed message logger (stub — not yet implemented).

    Intended schema
    ───────────────
    CREATE TABLE mqtt_messages (
        id          BIGSERIAL PRIMARY KEY,
        received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        topic       TEXT        NOT NULL,
        payload     TEXT,
        qos         SMALLINT    NOT NULL,
        retain      BOOLEAN     NOT NULL DEFAULT FALSE
    );

    CREATE INDEX ON mqtt_messages (topic);
    CREATE INDEX ON mqtt_messages (received_at DESC);

    Connection string is expected in the constructor:
        logger = DatabaseLogger("postgresql://user:pass@host:5432/dbname")

    Dependencies:
        pip install psycopg[binary]   # or asyncpg for async variant
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        raise NotImplementedError(
            "DatabaseLogger is a stub. "
            "Implement using psycopg3 or asyncpg with the schema shown in the docstring."
        )

    def store_message(self, msg: "MqttMessage") -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    @property
    def info(self) -> str:
        return f"postgresql:{self._dsn}"
