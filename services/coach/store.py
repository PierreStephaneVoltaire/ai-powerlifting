import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TERMINAL = {"succeeded", "failed", "cancelled", "uncertain"}


@dataclass
class Job:
    job_id: str
    owner: str
    athlete: str
    kind: str
    conversation_id: str
    payload: dict[str, Any]
    status: str = "queued"
    result: Any = None
    error: dict[str, Any] | None = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))

    def view(self) -> dict[str, Any]:
        content = None if self.result is None else self.result if isinstance(self.result, str) else json.dumps(self.result, default=str)
        return {
            "job_id": self.job_id,
            "status": self.status,
            "kind": self.kind,
            "conversation_id": self.conversation_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "artifacts": [],
            "result": None if content is None else {"content": content},
        }


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, owner TEXT, athlete TEXT, kind TEXT, conversation_id TEXT,
                payload TEXT, status TEXT, result TEXT, error TEXT, created_at INTEGER, updated_at INTEGER);
            CREATE TABLE IF NOT EXISTS threads (owner TEXT, conversation_id TEXT, thread_id TEXT, PRIMARY KEY (owner, conversation_id));
            """
        )
        self.db.execute("UPDATE jobs SET status='uncertain', error=? WHERE status IN ('queued', 'running')", (json.dumps({"code": "interrupted", "message": "Coach restarted during this job; check side effects before retrying"}),))
        self.db.commit()

    def _row(self, row) -> Job:
        return Job(job_id=row[0], owner=row[1], athlete=row[2], kind=row[3], conversation_id=row[4], payload=json.loads(row[5]), status=row[6],
                   result=json.loads(row[7]) if row[7] else None, error=json.loads(row[8]) if row[8] else None, created_at=row[9], updated_at=row[10])

    def create(self, owner: str, athlete: str, kind: str, conversation_id: str, payload: dict[str, Any]) -> Job:
        with self.lock:
            job = Job(job_id=uuid.uuid4().hex, owner=owner, athlete=athlete, kind=kind, conversation_id=conversation_id, payload=payload)
            self.db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)", (job.job_id, owner, athlete, kind, conversation_id, json.dumps(payload, default=str), job.status, None, None, job.created_at, job.updated_at))
            self.db.commit()
            return job

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._row(row) if row else None

    def update(self, job: Job) -> None:
        job.updated_at = int(time.time())
        with self.lock:
            self.db.execute("UPDATE jobs SET status=?, result=?, error=?, updated_at=? WHERE job_id=?", (job.status, None if job.result is None else json.dumps(job.result, default=str), None if job.error is None else json.dumps(job.error), job.updated_at, job.job_id))
            self.db.commit()

    def thread(self, owner: str, conversation_id: str) -> str | None:
        with self.lock:
            row = self.db.execute("SELECT thread_id FROM threads WHERE owner=? AND conversation_id=?", (owner, conversation_id)).fetchone()
        return row[0] if row else None

    def bind_thread(self, owner: str, conversation_id: str, thread_id: str) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO threads VALUES (?,?,?)", (owner, conversation_id, thread_id))
            self.db.commit()

    def forget_thread(self, owner: str, conversation_id: str) -> None:
        with self.lock:
            self.db.execute("DELETE FROM threads WHERE owner=? AND conversation_id=?", (owner, conversation_id))
            self.db.commit()
