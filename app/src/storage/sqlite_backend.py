



from __future__ import annotations
import logging
from typing import List, Optional

from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy import text

from config import STORAGE_DB_PATH
from storage.models import WebhookRecord

logger = logging.getLogger(__name__)

_engine = None

def init_sqlite() -> None:





    global _engine
    _engine = create_engine(
        f"sqlite:///{STORAGE_DB_PATH}",
        connect_args={"check_same_thread": False},
        echo=False,
    )

    with _engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()

    SQLModel.metadata.create_all(_engine)

    with _engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(routing_cache)"))
        existing_cols = {row[1] for row in result.fetchall()}

        migrations = [
            ("current_tier", "INTEGER DEFAULT 0"),
            ("context_tokens", "INTEGER DEFAULT 0"),
            ("condensation_count", "INTEGER DEFAULT 0"),
            ("pinned_tier", "INTEGER"),
            ("pondering", "INTEGER DEFAULT 0"),
        ]

        for col_name, col_def in migrations:
            if col_name not in existing_cols:
                conn.execute(text(f"ALTER TABLE routing_cache ADD COLUMN {col_name} {col_def}"))
                logger.info(f"[Migration] Added column {col_name} to routing_cache")

        conn.commit()

    with _engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(webhooks)"))
        existing_cols = {row[1] for row in result.fetchall()}

        webhook_migrations = [
            ("pinned_specialist", "TEXT NOT NULL DEFAULT ''"),
        ]

        for col_name, col_def in webhook_migrations:
            if col_name not in existing_cols:
                conn.execute(text(f"ALTER TABLE webhooks ADD COLUMN {col_name} {col_def}"))
                logger.info(f"[Migration] Added column {col_name} to webhooks")

        conn.commit()

    logger.info(f"SQLite store initialized at {STORAGE_DB_PATH} (WAL mode)")

def close_sqlite() -> None:




    global _engine
    if _engine:
        _engine.dispose()
        _engine = None
        logger.info("SQLite store closed")

class _SQLiteBackend:





    def __init__(self):
        pass
    
    @property
    def engine(self):








        if _engine is None:
            raise RuntimeError("SQLite not initialized. Call init_sqlite().")
        return _engine
    
    def get_session(self) -> Session:








        if _engine is None:
            raise RuntimeError("SQLite not initialized. Call init_sqlite().")
        return Session(_engine)

class SQLiteWebhookStore:

    
    def __init__(self):

        self._backend = _SQLiteBackend()
    
    def _session(self) -> Session:








        if _engine is None:
            raise RuntimeError("SQLite not initialized. Call init_sqlite().")
        return Session(_engine)

    def create(self, record: WebhookRecord) -> WebhookRecord:








        with self._session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get(self, webhook_id: str) -> Optional[WebhookRecord]:








        with self._session() as session:
            return session.get(WebhookRecord, webhook_id)

    def list_all(self) -> List[WebhookRecord]:





        with self._session() as session:
            statement = select(WebhookRecord)
            return list(session.exec(statement).all())

    def list_active(self) -> List[WebhookRecord]:





        with self._session() as session:
            statement = select(WebhookRecord).where(
                WebhookRecord.status == "active"
            )
            return list(session.exec(statement).all())

    def deactivate(self, webhook_id: str) -> bool:








        with self._session() as session:
            record = session.get(WebhookRecord, webhook_id)
            if record is None:
                return False
            record.status = "inactive"
            session.add(record)
            session.commit()
            return True
