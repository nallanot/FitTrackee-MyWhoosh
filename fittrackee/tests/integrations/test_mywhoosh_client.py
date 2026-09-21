from datetime import timezone
from unittest.mock import patch

import pytest
from flask import Flask

from fittrackee.integrations.crypto import decrypt_token, encrypt_token
from fittrackee.integrations.mywhoosh_client import (
    MyWhooshActivity,
    MyWhooshClient,
    MyWhooshClientError,
)


class TestMyWhooshActivity:
    def test_it_parses_iso_activity_date(self) -> None:
        activity = MyWhooshActivity.from_payload(
            {
                "id": "activity-1",
                "activityFileId": "file-1",
                "title": "Morning ride",
                "startDatetime": "2026-09-20T12:34:56.000Z",
            }
        )

        assert activity.activity_id == "activity-1"
        assert activity.activity_file_id == "file-1"
        assert activity.activity_date is not None
        assert activity.activity_date.tzinfo == timezone.utc

    def test_it_parses_millisecond_timestamp(self) -> None:
        activity = MyWhooshActivity.from_payload(
            {
                "id": "activity-1",
                "activityFileId": "file-1",
                "date": 1_758_371_696_000,
            }
        )

        assert activity.activity_date is not None
        assert activity.activity_date.year == 2025


class TestMyWhooshClient:
    def test_it_logs_in_without_retaining_password(self) -> None:
        client = MyWhooshClient()
        with patch.object(
            client,
            "_json_request",
            return_value={
                "Success": True,
                "AccessToken": "secret-token",
                "WhooshId": "whoosh-1",
            },
        ) as request_mock:
            session = client.login("rider@example.com", "password")

        assert session.access_token == "secret-token"
        assert session.whoosh_id == "whoosh-1"
        assert not hasattr(client, "password")
        assert request_mock.call_args.args[1]["Password"] == "password"

    @pytest.mark.parametrize(
        "url",
        [
            "http://bucket.s3.amazonaws.com/activity.fit",
            "file:///etc/passwd",
            "https://example.com/activity.fit",
        ],
    )
    def test_it_rejects_unsafe_download_urls(self, url: str) -> None:
        with pytest.raises(MyWhooshClientError):
            MyWhooshClient._validate_download_url(url)


class TestIntegrationTokenEncryption:
    def test_it_encrypts_and_decrypts_token(self) -> None:
        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test-secret"
        with app.app_context():
            encrypted = encrypt_token("my-token")

            assert encrypted != "my-token"
            assert decrypt_token(encrypted) == "my-token"
