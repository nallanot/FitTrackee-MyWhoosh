from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Mapped, mapped_column, relationship

from fittrackee import BaseModel, db
from fittrackee.database import TZDateTime
from fittrackee.dates import aware_utc_now
from fittrackee.utils import encode_uuid


class MyWhooshConnection(BaseModel):
    __tablename__ = "mywhoosh_connections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    email: Mapped[Optional[str]] = mapped_column(db.String(255), nullable=True)
    whoosh_id: Mapped[Optional[str]] = mapped_column(
        db.String(255), nullable=True
    )
    access_token: Mapped[Optional[str]] = mapped_column(db.Text, nullable=True)
    auto_sync: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )
    sync_days: Mapped[int] = mapped_column(
        nullable=False, default=30, server_default="30"
    )
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, default=aware_utc_now
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TZDateTime, nullable=True, onupdate=aware_utc_now
    )
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(
        TZDateTime, nullable=True
    )
    last_sync_status: Mapped[str] = mapped_column(
        db.String(30), nullable=False, default="never", server_default="never"
    )
    last_error: Mapped[Optional[str]] = mapped_column(db.Text, nullable=True)
    sync_in_progress: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )
    sync_started_at: Mapped[Optional[datetime]] = mapped_column(
        TZDateTime, nullable=True
    )

    imports: Mapped[List["MyWhooshImport"]] = relationship(
        "MyWhooshImport",
        back_populates="connection",
        cascade="all, delete-orphan",
        order_by="MyWhooshImport.imported_at.desc()",
    )

    @property
    def connected(self) -> bool:
        return bool(self.access_token and self.whoosh_id)

    def serialize(self, include_imports: bool = True) -> Dict:
        data: Dict = {
            "connected": self.connected,
            "email": self.email if self.connected else None,
            "auto_sync": self.auto_sync,
            "sync_days": self.sync_days,
            "last_sync_at": self.last_sync_at,
            "last_sync_status": self.last_sync_status,
            "last_error": self.last_error,
            "sync_in_progress": self.sync_in_progress,
        }
        if include_imports:
            data["imports"] = [item.serialize() for item in self.imports[:10]]
        return data


class MyWhooshImport(BaseModel):
    __tablename__ = "mywhoosh_imports"
    __table_args__ = (
        db.UniqueConstraint(
            "connection_id",
            "activity_id",
            name="mywhoosh_import_connection_activity_unique",
        ),
        db.UniqueConstraint(
            "connection_id",
            "activity_file_id",
            name="mywhoosh_import_connection_file_unique",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        db.ForeignKey("mywhoosh_connections.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    activity_id: Mapped[str] = mapped_column(db.String(255), nullable=False)
    activity_file_id: Mapped[str] = mapped_column(
        db.String(255), nullable=False
    )
    activity_title: Mapped[Optional[str]] = mapped_column(
        db.String(255), nullable=True
    )
    activity_date: Mapped[Optional[datetime]] = mapped_column(
        TZDateTime, nullable=True
    )
    file_sha256: Mapped[Optional[str]] = mapped_column(
        db.String(64), nullable=True
    )
    workout_id: Mapped[Optional[int]] = mapped_column(
        db.ForeignKey("workouts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        db.String(20), nullable=False, default="pending"
    )
    error: Mapped[Optional[str]] = mapped_column(db.Text, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, default=aware_utc_now
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TZDateTime, nullable=True, onupdate=aware_utc_now
    )

    connection: Mapped["MyWhooshConnection"] = relationship(
        "MyWhooshConnection", back_populates="imports"
    )
    workout = relationship("Workout", uselist=False)

    def serialize(self) -> Dict:
        return {
            "activity_id": self.activity_id,
            "activity_title": self.activity_title,
            "activity_date": self.activity_date,
            "status": self.status,
            "error": self.error,
            "imported_at": self.imported_at,
            "workout_id": (
                encode_uuid(self.workout.uuid) if self.workout else None
            ),
        }
