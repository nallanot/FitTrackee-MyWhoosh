import hashlib
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Dict, Optional

from flask import current_app
from sqlalchemy import or_
from werkzeug.datastructures import FileStorage

from fittrackee import appLog, db
from fittrackee.files import (
    check_mime_type,
    get_absolute_file_path,
)
from fittrackee.users.models import User
from fittrackee.workouts.constants import WORKOUT_FILE_DETECTED_MIMETYPES
from fittrackee.workouts.models import Sport, Workout
from fittrackee.workouts.services.workouts_from_file_creation_service import (
    WorkoutsFromFileCreationService,
)

from .crypto import IntegrationTokenError, decrypt_token
from .models import MyWhooshConnection, MyWhooshImport
from .mywhoosh_client import (
    MyWhooshActivity,
    MyWhooshClient,
    MyWhooshClientError,
)


class MyWhooshSyncInProgress(Exception):
    pass


class MyWhooshNotConnected(Exception):
    def __init__(self) -> None:
        super().__init__("MyWhoosh is not connected")


class MyWhooshSyncService:
    LOCK_TIMEOUT = timedelta(minutes=30)

    def __init__(
        self,
        connection: MyWhooshConnection,
        client: Optional[MyWhooshClient] = None,
    ):
        self.connection = connection
        self.user = User.query.filter_by(id=connection.user_id).one()
        if client is None:
            if not connection.access_token:
                raise MyWhooshNotConnected()
            try:
                token = decrypt_token(connection.access_token)
            except IntegrationTokenError as exc:
                connection.last_sync_status = "needs_reconnect"
                connection.last_error = str(exc)
                db.session.commit()
                raise
            client = MyWhooshClient(token)
        self.client = client

    def _claim(self) -> None:
        stale_before = datetime.now(timezone.utc) - self.LOCK_TIMEOUT
        updated = (
            db.session.query(MyWhooshConnection)
            .filter(
                MyWhooshConnection.id == self.connection.id,
                or_(
                    MyWhooshConnection.sync_in_progress == False,  # noqa: E712
                    MyWhooshConnection.sync_started_at < stale_before,
                ),
            )
            .update(
                {
                    "sync_in_progress": True,
                    "sync_started_at": datetime.now(timezone.utc),
                    "last_error": None,
                },
                synchronize_session=False,
            )
        )
        db.session.commit()
        if not updated:
            raise MyWhooshSyncInProgress()
        db.session.refresh(self.connection)

    def _finish(self, status: str, error: Optional[str] = None) -> None:
        connection = MyWhooshConnection.query.filter_by(
            id=self.connection.id
        ).one()
        connection.sync_in_progress = False
        connection.sync_started_at = None
        connection.last_sync_at = datetime.now(timezone.utc)
        connection.last_sync_status = status
        connection.last_error = error
        db.session.commit()

    @staticmethod
    def _remove_workout_files(workout: Optional[Workout]) -> None:
        if workout is None:
            return
        for relative_path in (workout.original_file, workout.map):
            if not relative_path:
                continue
            absolute_path = get_absolute_file_path(relative_path)
            if os.path.isfile(absolute_path):
                os.remove(absolute_path)

    def _get_or_create_import(
        self, activity: MyWhooshActivity
    ) -> MyWhooshImport:
        import_record = MyWhooshImport.query.filter(
            MyWhooshImport.connection_id == self.connection.id,
            or_(
                MyWhooshImport.activity_id == activity.activity_id,
                MyWhooshImport.activity_file_id == activity.activity_file_id,
            ),
        ).first()
        if import_record is None:
            import_record = MyWhooshImport(
                connection_id=self.connection.id,
                activity_id=activity.activity_id,
                activity_file_id=activity.activity_file_id,
                activity_title=activity.title[:255],
                activity_date=activity.activity_date,
            )
            db.session.add(import_record)
        else:
            import_record.activity_file_id = activity.activity_file_id
            import_record.activity_title = activity.title[:255]
            import_record.activity_date = activity.activity_date
        import_record.status = "pending"
        import_record.error = None
        return import_record

    def _record_failure(
        self, activity: MyWhooshActivity, error: Exception
    ) -> None:
        import_record = self._get_or_create_import(activity)
        import_record.status = "failed"
        import_record.error = str(error)[:2000]
        import_record.updated_at = datetime.now(timezone.utc)
        db.session.commit()

    def _import_activity(self, activity: MyWhooshActivity) -> None:
        fit_data = self.client.download_fit(
            activity.activity_file_id,
            int(current_app.config["max_single_file_size"]),
        )
        fit_stream = BytesIO(fit_data)
        check_mime_type("fit", fit_stream, WORKOUT_FILE_DETECTED_MIMETYPES)

        sport = Sport.query.filter_by(label="Cycling (Virtual)").first()
        if sport is None or not sport.is_active:
            raise MyWhooshClientError(
                "Cycling (Virtual) is not enabled on this FitTrackee instance"
            )

        file_storage = FileStorage(
            stream=fit_stream,
            filename=f"mywhoosh-{activity.activity_id}.fit",
            content_type="application/vnd.ant.fit",
        )
        workout: Optional[Workout] = None
        try:
            import_record = self._get_or_create_import(activity)
            service = WorkoutsFromFileCreationService(
                self.user,
                {
                    "sport_id": sport.id,
                    "title": activity.title,
                    "notes": "Imported automatically from MyWhoosh.",
                },
                file_storage,
            )
            workout = service.create_workout_from_file(
                "fit",
                service.get_equipments(),
                get_weather=False,
                is_single_workout=True,
                commit=False,
            )
            import_record.workout_id = workout.id
            import_record.file_sha256 = hashlib.sha256(fit_data).hexdigest()
            import_record.status = "imported"
            import_record.error = None
            import_record.imported_at = datetime.now(timezone.utc)
            db.session.commit()
        except Exception:
            db.session.rollback()
            self._remove_workout_files(workout)
            raise

    def sync(self, days: Optional[int] = None) -> Dict:
        self._claim()
        sync_days = days if days is not None else self.connection.sync_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=sync_days)
        summary = {"imported": 0, "skipped": 0, "failed": 0}
        try:
            activities = self.client.get_activities()
            for activity in activities:
                if activity.activity_date and activity.activity_date < cutoff:
                    continue
                existing = MyWhooshImport.query.filter(
                    MyWhooshImport.connection_id == self.connection.id,
                    MyWhooshImport.status == "imported",
                    or_(
                        MyWhooshImport.activity_id == activity.activity_id,
                        MyWhooshImport.activity_file_id
                        == activity.activity_file_id,
                    ),
                ).first()
                if existing:
                    summary["skipped"] += 1
                    continue
                try:
                    self._import_activity(activity)
                    summary["imported"] += 1
                except Exception as exc:
                    db.session.rollback()
                    if (
                        isinstance(exc, MyWhooshClientError)
                        and exc.needs_reconnect
                    ):
                        raise
                    appLog.exception(
                        "Unable to import MyWhoosh activity %s",
                        activity.activity_id,
                    )
                    self._record_failure(activity, exc)
                    summary["failed"] += 1

            status = "partial" if summary["failed"] else "success"
            error = (
                f"{summary['failed']} activity import(s) failed"
                if summary["failed"]
                else None
            )
            self._finish(status, error)
            return summary
        except (MyWhooshClientError, IntegrationTokenError) as exc:
            db.session.rollback()
            status = (
                "needs_reconnect"
                if getattr(exc, "needs_reconnect", False)
                or isinstance(exc, IntegrationTokenError)
                else "error"
            )
            self._finish(status, str(exc))
            raise
        except Exception as exc:
            db.session.rollback()
            self._finish("error", "Unexpected synchronization error")
            raise exc
