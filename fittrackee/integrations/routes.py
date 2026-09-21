from typing import Dict, Tuple, Union

from flask import Blueprint, request

from fittrackee import db
from fittrackee.oauth2.server import require_auth
from fittrackee.responses import HttpResponse, InvalidPayloadErrorResponse
from fittrackee.users.models import User

from .crypto import IntegrationTokenError, encrypt_token
from .models import MyWhooshConnection
from .mywhoosh_client import MyWhooshClient, MyWhooshClientError
from .mywhoosh_service import (
    MyWhooshNotConnected,
    MyWhooshSyncInProgress,
    MyWhooshSyncService,
)

integrations_blueprint = Blueprint("integrations", __name__)


def _get_connection(user_id: int) -> MyWhooshConnection:
    connection = MyWhooshConnection.query.filter_by(user_id=user_id).first()
    if connection is None:
        connection = MyWhooshConnection(user_id=user_id)
        db.session.add(connection)
        db.session.commit()
    return connection


@integrations_blueprint.route("/integrations/mywhoosh", methods=["GET"])
@require_auth(scopes=["users:read"])
def get_mywhoosh_connection(auth_user: User) -> Dict:
    connection = _get_connection(auth_user.id)
    return {"status": "success", "data": connection.serialize()}


@integrations_blueprint.route(
    "/integrations/mywhoosh/connect", methods=["POST"]
)
@require_auth(scopes=["users:write"])
def connect_mywhoosh(
    auth_user: User,
) -> Union[Tuple[Dict, int], InvalidPayloadErrorResponse]:
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")
    if not email or not password:
        return InvalidPayloadErrorResponse("email and password are required")
    try:
        session = MyWhooshClient().login(email, password)
    except MyWhooshClientError as exc:
        return {
            "status": "error",
            "message": str(exc),
        }, 400

    connection = _get_connection(auth_user.id)
    connection.email = email
    connection.whoosh_id = session.whoosh_id
    connection.access_token = encrypt_token(session.access_token)
    connection.last_sync_status = "never"
    connection.last_error = None
    db.session.commit()
    return {"status": "success", "data": connection.serialize()}, 200


@integrations_blueprint.route(
    "/integrations/mywhoosh/settings", methods=["PATCH"]
)
@require_auth(scopes=["users:write"])
def update_mywhoosh_settings(
    auth_user: User,
) -> Union[Dict, InvalidPayloadErrorResponse]:
    connection = _get_connection(auth_user.id)
    payload = request.get_json(silent=True) or {}
    if "auto_sync" in payload:
        if not isinstance(payload["auto_sync"], bool):
            return InvalidPayloadErrorResponse("auto_sync must be a boolean")
        connection.auto_sync = payload["auto_sync"]
    if "sync_days" in payload:
        try:
            sync_days = int(payload["sync_days"])
        except (TypeError, ValueError):
            return InvalidPayloadErrorResponse("sync_days must be an integer")
        if sync_days < 1 or sync_days > 365:
            return InvalidPayloadErrorResponse(
                "sync_days must be between 1 and 365"
            )
        connection.sync_days = sync_days
    db.session.commit()
    return {"status": "success", "data": connection.serialize()}


@integrations_blueprint.route("/integrations/mywhoosh/sync", methods=["POST"])
@require_auth(scopes=["workouts:write"])
def sync_mywhoosh(
    auth_user: User,
) -> Union[Tuple[Dict, int], HttpResponse]:
    connection = _get_connection(auth_user.id)
    if not connection.connected:
        return HttpResponse(
            {"status": "error", "message": "MyWhoosh is not connected"},
            status_code=409,
        )
    try:
        summary = MyWhooshSyncService(connection).sync()
    except MyWhooshSyncInProgress:
        return HttpResponse(
            {
                "status": "error",
                "message": "MyWhoosh synchronization is already in progress",
            },
            status_code=409,
        )
    except (
        IntegrationTokenError,
        MyWhooshClientError,
        MyWhooshNotConnected,
    ) as exc:
        return HttpResponse(
            {"status": "error", "message": str(exc)}, status_code=502
        )
    connection = MyWhooshConnection.query.filter_by(id=connection.id).one()
    return {
        "status": "success",
        "data": {"summary": summary, "connection": connection.serialize()},
    }, 200


@integrations_blueprint.route(
    "/integrations/mywhoosh/disconnect", methods=["DELETE"]
)
@require_auth(scopes=["users:write"])
def disconnect_mywhoosh(auth_user: User) -> Tuple[Dict, int]:
    connection = _get_connection(auth_user.id)
    connection.email = None
    connection.whoosh_id = None
    connection.access_token = None
    connection.auto_sync = False
    connection.last_sync_status = "disconnected"
    connection.last_error = None
    db.session.commit()
    return {"status": "success", "data": connection.serialize()}, 200
