import logging

import click

from fittrackee import db
from fittrackee.cli.app import app
from fittrackee.users.models import User

from .models import MyWhooshConnection
from .mywhoosh_service import MyWhooshSyncService

logger = logging.getLogger("fittrackee_integrations_cli")
logger.setLevel(logging.INFO)


@click.group(name="integrations")
def integrations_cli() -> None:
    """Manage external service integrations."""


@integrations_cli.command("mywhoosh-sync")
@click.option("--username", help="Sync only one FitTrackee user.")
def sync_mywhoosh_connections(username: str | None) -> None:
    """Synchronize connected MyWhoosh accounts with automatic sync enabled."""
    with app.app_context():
        query = MyWhooshConnection.query.filter_by(
            auto_sync=True,
        ).filter(MyWhooshConnection.access_token.is_not(None))
        if username:
            user = User.query.filter_by(username=username).first()
            if user is None:
                raise click.ClickException(f"user '{username}' does not exist")
            query = query.filter_by(user_id=user.id)

        connections = query.order_by(MyWhooshConnection.id).all()
        failed = 0
        for connection in connections:
            try:
                summary = MyWhooshSyncService(connection).sync()
                logger.info(
                    "MyWhoosh sync for user %s: %s",
                    connection.user_id,
                    summary,
                )
            except Exception as exc:
                db.session.rollback()
                failed += 1
                logger.error(
                    "MyWhoosh sync failed for user %s: %s",
                    connection.user_id,
                    exc,
                )
        if failed:
            raise click.ClickException(
                f"{failed} MyWhoosh synchronization(s) failed"
            )
