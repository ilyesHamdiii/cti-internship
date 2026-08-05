from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Self

import httpx
from pydantic import SecretStr

from app.models.models import MispPollState, Setting
from app.services import misp
from app.services.misp import MispConnectivityService, MispIngestionScheduleService


class DummyDb:
    def __init__(self, state: MispPollState | None = None):
        self.state = state

    def get(self, model: object, key: object) -> MispPollState | None:
        return self.state


class DummyScheduleDb:
    def __init__(self) -> None:
        self.items: dict[str, Setting] = {}

    def get(self, model: object, key: object) -> Setting | None:
        return self.items.get(str(key))

    def add(self, item: Setting) -> None:
        self.items[item.key] = item

    def commit(self) -> None:
        pass


def settings(api_key: str | None = "key") -> SimpleNamespace:
    return SimpleNamespace(
        misp_url="https://misp",
        misp_api_key=SecretStr(api_key) if api_key else None,
        misp_verify_tls=False,
    )


def test_misp_connectivity_reports_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(misp, "get_settings", lambda: settings(api_key=None))

    result = MispConnectivityService(DummyDb()).check()

    assert result["status"] == "not_configured"
    assert result["configured"] is False


def test_misp_connectivity_reports_authentication_failed(monkeypatch) -> None:
    class Client:
        def __init__(self, **_: object):
            pass

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def get(self, url: str, **_: object) -> httpx.Response:
            if url.endswith("/users/heartbeat"):
                return httpx.Response(200)
            return httpx.Response(403)

    monkeypatch.setattr(misp, "get_settings", lambda: settings())
    monkeypatch.setattr(httpx, "Client", Client)

    result = MispConnectivityService(DummyDb()).check()

    assert result["status"] == "authentication_failed"
    assert result["reachable"] is True
    assert result["authenticated"] is False


def test_misp_connectivity_reports_healthy_after_poll(monkeypatch) -> None:
    class Client:
        def __init__(self, **_: object):
            pass

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def get(self, _: str, **__: object) -> httpx.Response:
            return httpx.Response(200, json={"version": "2.5"})

    state = MispPollState(id=1, last_event_id="42", updated_at=datetime.now(UTC))
    monkeypatch.setattr(misp, "get_settings", lambda: settings())
    monkeypatch.setattr(httpx, "Client", Client)

    result = MispConnectivityService(DummyDb(state)).check()

    assert result["status"] == "healthy"
    assert result["configured"] is True
    assert result["reachable"] is True
    assert result["authenticated"] is True
    assert result["polling_successfully"] is True


def test_misp_schedule_can_disable_scheduled_polling() -> None:
    db = DummyScheduleDb()
    schedule = MispIngestionScheduleService(db).update({"mode": "disabled", "enabled": False})

    due = MispIngestionScheduleService(db).due_status()

    assert schedule["mode"] == "disabled"
    assert due["configured"] is True
    assert due["due"] is False


def test_misp_schedule_stores_daily_next_run() -> None:
    db = DummyScheduleDb()
    schedule = MispIngestionScheduleService(db).update(
        {"mode": "daily", "enabled": True, "time_of_day": "09:30", "timezone_offset_minutes": 60}
    )

    assert schedule["mode"] == "daily"
    assert schedule["enabled"] is True
    assert schedule["time_of_day"] == "09:30"
    assert schedule["next_run_at"]
