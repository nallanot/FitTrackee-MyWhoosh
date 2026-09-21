import ipaddress
import json
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

LOGIN_URL = "https://services.mywhoosh.com/http-service/api/login"
ACTIVITIES_URL = "https://service14.mywhoosh.com/v2/rider/profile/activities"
DOWNLOAD_URL = (
    "https://service14.mywhoosh.com/v2/rider/profile/download-activity-file"
)
ALLOWED_DOWNLOAD_HOST_SUFFIXES = (
    ".amazonaws.com",
    ".amazonaws.com.cn",
    ".mywhoosh.com",
    ".cloudfront.net",
)


class MyWhooshClientError(Exception):
    def __init__(self, message: str, *, needs_reconnect: bool = False):
        super().__init__(message)
        self.needs_reconnect = needs_reconnect


@dataclass
class MyWhooshSession:
    access_token: str
    whoosh_id: str


@dataclass
class MyWhooshActivity:
    activity_id: str
    activity_file_id: str
    title: str
    activity_date: Optional[datetime]

    @classmethod
    def from_payload(cls, payload: Dict) -> "MyWhooshActivity":
        raw_date = payload.get("startDatetime")
        activity_date: Optional[datetime] = None
        if raw_date:
            try:
                activity_date = datetime.fromisoformat(
                    str(raw_date).replace("Z", "+00:00")
                )
                if activity_date.tzinfo is None:
                    activity_date = activity_date.replace(tzinfo=timezone.utc)
            except ValueError:
                activity_date = None
        if activity_date is None and payload.get("date") is not None:
            try:
                timestamp = float(payload["date"])
                if timestamp > 100_000_000_000:
                    timestamp /= 1000
                activity_date = datetime.fromtimestamp(
                    timestamp, tz=timezone.utc
                )
            except (TypeError, ValueError, OSError):
                activity_date = None
        return cls(
            activity_id=str(payload.get("id", "")),
            activity_file_id=str(payload.get("activityFileId", "")),
            title=str(payload.get("title") or "MyWhoosh"),
            activity_date=activity_date,
        )


class MyWhooshClient:
    def __init__(self, access_token: Optional[str] = None, timeout: int = 30):
        self.access_token = access_token
        self.timeout = timeout

    def _json_request(
        self, url: str, payload: Dict, *, authenticated: bool = True
    ) -> Dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "FitTrackee-MyWhoosh/1.0",
        }
        if authenticated:
            if not self.access_token:
                raise MyWhooshClientError(
                    "MyWhoosh account is not connected", needs_reconnect=True
                )
            headers["Authorization"] = f"Bearer {self.access_token}"
        request = Request(  # noqa: S310 - URLs are fixed HTTPS constants
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(  # noqa: S310 - URLs are fixed HTTPS constants
                request, timeout=self.timeout
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            needs_reconnect = exc.code in (401, 403)
            raise MyWhooshClientError(
                f"MyWhoosh returned HTTP {exc.code}",
                needs_reconnect=needs_reconnect,
            ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise MyWhooshClientError(
                "MyWhoosh is temporarily unavailable"
            ) from exc

    def login(self, email: str, password: str) -> MyWhooshSession:
        result = self._json_request(
            LOGIN_URL,
            {
                "Username": email,
                "Password": password,
                "Platform": "Android",
                "Action": 1001,
                "CorrelationId": str(uuid4()),
                "DeviceId": str(uuid4()),
                "Authorization": "",
            },
            authenticated=False,
        )
        if not result.get("Success"):
            raise MyWhooshClientError(
                str(result.get("Message") or "MyWhoosh authentication failed"),
                needs_reconnect=True,
            )
        token = str(result.get("AccessToken") or "")
        whoosh_id = str(result.get("WhooshId") or "")
        if not token or not whoosh_id:
            raise MyWhooshClientError(
                "MyWhoosh did not return a usable session",
                needs_reconnect=True,
            )
        self.access_token = token
        return MyWhooshSession(access_token=token, whoosh_id=whoosh_id)

    def get_activities(self, max_pages: int = 50) -> List[MyWhooshActivity]:
        activities: List[MyWhooshActivity] = []
        for page in range(1, max_pages + 1):
            result = self._json_request(
                ACTIVITIES_URL, {"sortDate": "DESC", "page": page}
            )
            data = result.get("data") or {}
            for payload in data.get("results") or []:
                activity = MyWhooshActivity.from_payload(payload)
                if activity.activity_id and activity.activity_file_id:
                    activities.append(activity)
            total_pages = int(data.get("totalPages") or 1)
            if page >= total_pages:
                break
        return activities

    @staticmethod
    def _validate_download_url(url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host:
            raise MyWhooshClientError(
                "MyWhoosh returned an unsafe download URL"
            )
        if not any(
            host.endswith(suffix) for suffix in ALLOWED_DOWNLOAD_HOST_SUFFIXES
        ):
            raise MyWhooshClientError(
                "MyWhoosh returned an untrusted download host"
            )
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, 443)}
            if any(
                not ipaddress.ip_address(address).is_global
                for address in addresses
            ):
                raise MyWhooshClientError(
                    "MyWhoosh download host resolves to a private address"
                )
        except socket.gaierror as exc:
            raise MyWhooshClientError(
                "MyWhoosh download host could not be resolved"
            ) from exc

    def download_fit(self, activity_file_id: str, max_size: int) -> bytes:
        result = self._json_request(DOWNLOAD_URL, {"fileId": activity_file_id})
        download_url = result.get("data")
        if not isinstance(download_url, str) or not download_url:
            raise MyWhooshClientError("MyWhoosh did not return a FIT file URL")
        self._validate_download_url(download_url)
        request = Request(  # noqa: S310 - URL is validated above
            download_url,
            headers={"User-Agent": "FitTrackee-MyWhoosh/1.0"},
            method="GET",
        )
        try:
            with urlopen(  # noqa: S310 - URL is validated above
                request, timeout=self.timeout
            ) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > max_size:
                    raise MyWhooshClientError("MyWhoosh FIT file is too large")
                content = response.read(max_size + 1)
        except HTTPError as exc:
            raise MyWhooshClientError(
                f"FIT download returned HTTP {exc.code}"
            ) from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise MyWhooshClientError("FIT download failed") from exc
        if len(content) > max_size:
            raise MyWhooshClientError("MyWhoosh FIT file is too large")
        return content
