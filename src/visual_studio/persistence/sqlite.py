"""SQLite persistence (self-initializing schema).

A thin, dependency-inverted storage layer. It speaks the domain
:class:`GenerationTask` model and converts to/from SQLAlchemy rows. Each public
method opens its own short-lived session, which keeps it safe to call from both
the API request handlers and the background worker thread (sqlite is configured
with ``check_same_thread=False``).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Column,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from visual_studio.domain.models import GenerationTask, TaskStatus

Base = declarative_base()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TaskRow(Base):
    __tablename__ = "tasks"

    task_id = Column(String, primary_key=True)
    case_id = Column(String, index=True)
    platform = Column(String)
    image_type = Column(String)
    canvas = Column(String)
    selling_point = Column(String)
    # Added when real providers arrived: an attribute-only selling point does
    # not identify the product being depicted.
    product_name = Column(String, default="")
    required_elements = Column(Text)
    forbidden_elements = Column(Text)
    style_preset = Column(String)
    priority = Column(Integer)
    prompt = Column(Text)
    status = Column(String, index=True)
    image_url = Column(Text, nullable=True)
    provider = Column(String, nullable=True)
    quality_flags = Column(Text)
    alignment_score = Column(Float, nullable=True)
    alignment_flags = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(String)
    updated_at = Column(String)


class EventRow(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String, index=True)
    case_id = Column(String, index=True)
    payload = Column(Text)
    created_at = Column(String)


class SqliteStore:
    """Persists tasks and events to a SQLite file."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(parent, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        self.Session = sessionmaker(bind=self.engine, future=True)

    # -- schema ---------------------------------------------------------
    def init_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        self._add_missing_columns()

    def _add_missing_columns(self) -> None:
        """Lightweight forward migration for columns added after first release.

        ``create_all`` never alters an existing table, so a database created by
        an older build would be missing newer columns.
        """
        new_columns = {"tasks": {"product_name": "VARCHAR"}}
        with self.engine.connect() as conn:
            for table, columns in new_columns.items():
                existing = {
                    row[1]
                    for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
                }
                for name, ddl_type in columns.items():
                    if name not in existing:
                        conn.exec_driver_sql(
                            f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"
                        )
            conn.commit()

    # -- tasks ----------------------------------------------------------
    def save_task(self, task: GenerationTask) -> None:
        row = self._task_to_row(task)
        with self.Session() as session:
            session.merge(row)
            session.commit()

    def get_task(self, task_id: str) -> Optional[GenerationTask]:
        with self.Session() as session:
            row = session.get(TaskRow, task_id)
            if row is None:
                return None
            return self._row_to_task(row)

    def get_highest_priority_queued(self) -> Optional[GenerationTask]:
        with self.Session() as session:
            row = (
                session.query(TaskRow)
                .filter(TaskRow.status == TaskStatus.QUEUED.value)
                .order_by(TaskRow.priority.desc(), TaskRow.created_at.asc())
                .limit(1)
                .one_or_none()
            )
            if row is None:
                return None
            return self._row_to_task(row)

    def list_tasks(self) -> list[GenerationTask]:
        with self.Session() as session:
            rows = session.query(TaskRow).all()
            return [self._row_to_task(r) for r in rows]

    # -- events ---------------------------------------------------------
    def append_event(self, event_type: str, case_id: Any, payload_json: str) -> None:
        row = EventRow(
            event_type=event_type,
            case_id=case_id,
            payload=payload_json,
            created_at=_now(),
        )
        with self.Session() as session:
            session.add(row)
            session.commit()

    def get_events(self, case_id: str, since_id: int = 0) -> list[dict[str, Any]]:
        with self.Session() as session:
            rows = (
                session.query(EventRow)
                .filter(EventRow.case_id == case_id, EventRow.id > since_id)
                .order_by(EventRow.id.asc())
                .all()
            )
            return [
                {
                    "id": r.id,
                    "event_type": r.event_type,
                    "case_id": r.case_id,
                    "payload": r.payload,
                }
                for r in rows
            ]

    # -- converters -----------------------------------------------------
    @staticmethod
    def _task_to_row(task: GenerationTask) -> TaskRow:
        now = _now()
        return TaskRow(
            task_id=task.task_id,
            case_id=task.case_id,
            platform=task.platform,
            image_type=task.image_type,
            canvas=task.canvas,
            selling_point=task.selling_point,
            product_name=task.product_name,
            required_elements=json.dumps(task.required_elements, ensure_ascii=False),
            forbidden_elements=json.dumps(task.forbidden_elements, ensure_ascii=False),
            style_preset=task.style_preset,
            priority=task.priority,
            prompt=task.prompt,
            status=task.status.value,
            image_url=task.image_url,
            provider=task.provider,
            quality_flags=json.dumps(task.quality_flags, ensure_ascii=False),
            alignment_score=task.alignment_score,
            alignment_flags=json.dumps(task.alignment_flags, ensure_ascii=False),
            error=task.error,
            created_at=task.created_at or now,
            updated_at=task.updated_at or now,
        )

    @staticmethod
    def _row_to_task(row: TaskRow) -> GenerationTask:
        return GenerationTask(
            task_id=row.task_id,
            case_id=row.case_id,
            platform=row.platform,
            image_type=row.image_type,
            canvas=row.canvas,
            selling_point=row.selling_point,
            product_name=getattr(row, "product_name", "") or "",
            required_elements=json.loads(row.required_elements or "[]"),
            forbidden_elements=json.loads(row.forbidden_elements or "[]"),
            style_preset=row.style_preset,
            priority=row.priority,
            prompt=row.prompt or "",
            status=TaskStatus(row.status),
            image_url=row.image_url,
            provider=row.provider,
            quality_flags=json.loads(row.quality_flags or "[]"),
            alignment_score=row.alignment_score,
            alignment_flags=json.loads(row.alignment_flags or "[]"),
            error=row.error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
