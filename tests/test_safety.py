import time
from unittest.mock import AsyncMock
import httpx
import pytest
from pydantic import ValidationError
from qbox.config import Settings
from qbox.history import History
from qbox.loxone import AdapterError, LoxoneAdapter
from qbox.models import Snapshot
from qbox.ollama import OllamaClient
from qbox.policy import EnergyService, PolicyError

TOKEN = "test-token-012345678901234567890123456789"


def config(tmp_path, **kwargs):
    return Settings(_env_file=None, mcp_token=TOKEN, history_path=tmp_path / "history.sqlite3", **kwargs)


def real(tmp_path, **kwargs):
    return config(tmp_path, demo_mode=False, loxone_username="user", loxone_password="secret",
                  loxone_grid_power="grid", loxone_pv_power="pv", loxone_battery_soc="soc",
                  loxone_battery_power="battery", loxone_ev_power="ev", **kwargs)


def telemetry(**kwargs):
    return Snapshot(timestamp=kwargs.get("timestamp", time.time()), source=kwargs.get("source", "loxone"),
                    grid_power=100, pv_power=200, battery_soc=50, battery_power=-100, ev_power=0)


def test_configuration_fails_closed(tmp_path):
    with pytest.raises(ValidationError):
        config(tmp_path, enable_ev_write=True)
    with pytest.raises(ValidationError):
        real(tmp_path, loxone_url="http://miniserver")
    with pytest.raises(ValidationError):
        config(tmp_path, loxone_ev_limit_input="../danger/On")


async def test_default_blocks_write(tmp_path):
    c = config(tmp_path)
    adapter = AsyncMock()
    history = History(c.history_path, 100)
    try:
        with pytest.raises(PolicyError):
            await EnergyService(c, adapter, history).set_ev_limit(1000)
        adapter.set_ev_limit.assert_not_called()
    finally:
        history.close()


@pytest.mark.parametrize("watts", [-1, 11001, float("nan"), True, 1.5])
async def test_bad_write_values(tmp_path, watts):
    c = real(tmp_path, observe_only=False, enable_ev_write=True,
             loxone_ev_limit_input="EVCap", loxone_watchdog_confirmed=True)
    history = History(c.history_path, 100)
    adapter = AsyncMock()
    try:
        with pytest.raises(PolicyError):
            await EnergyService(c, adapter, history).set_ev_limit(watts)
        adapter.set_ev_limit.assert_not_called()
    finally:
        history.close()


async def test_freshness_cooldown_and_audit(tmp_path):
    c = real(tmp_path, observe_only=False, enable_ev_write=True,
             loxone_ev_limit_input="EVCap", loxone_watchdog_confirmed=True)
    adapter = AsyncMock()
    history = History(c.history_path, 100)
    svc = EnergyService(c, adapter, history)
    try:
        adapter.snapshot.return_value = telemetry(timestamp=time.time() - 100)
        with pytest.raises(PolicyError):
            await svc.set_ev_limit(1000)
        adapter.set_ev_limit.assert_not_called()
        adapter.snapshot.return_value = telemetry()
        assert (await svc.set_ev_limit(1000))["physical_state_verified"] is False
        with pytest.raises(PolicyError):
            await svc.set_ev_limit(2000)
        adapter.set_ev_limit.assert_awaited_once_with(1000)
        assert history.recent()[0]["kind"] == "ev_write_accepted"
    finally:
        history.close()


async def test_uncertain_write_not_retried(tmp_path):
    c = real(tmp_path, observe_only=False, enable_ev_write=True,
             loxone_ev_limit_input="EVCap", loxone_watchdog_confirmed=True)
    adapter = AsyncMock()
    adapter.snapshot.return_value = telemetry()
    adapter.set_ev_limit.side_effect = TimeoutError()
    history = History(c.history_path, 100)
    try:
        svc = EnergyService(c, adapter, history)
        for _ in range(2):
            with pytest.raises(PolicyError):
                await svc.set_ev_limit(1000)
        adapter.set_ev_limit.assert_awaited_once()
        assert history.recent()[0]["kind"] == "ev_write_attempt"
    finally:
        history.close()


async def test_loxone_xml_mapping_and_auth(tmp_path):
    paths = []
    def handler(request):
        paths.append(request.url.path)
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(200, text='<LL value="42" Code="200"/>')
    adapter = LoxoneAdapter(real(tmp_path), httpx.MockTransport(handler))
    try:
        snap = await adapter.snapshot()
        assert snap.battery_soc == 42
        assert set(paths) == {f"/dev/sps/io/{name}/state" for name in ["grid", "pv", "soc", "battery", "ev"]}
    finally:
        await adapter.close()


@pytest.mark.parametrize("body", ['<LL value="NaN" Code="200"/>', '<LL value="1" Code="401"/>', 'invalid', '<LL value="101" Code="200"/>'])
async def test_invalid_loxone_response(tmp_path, body):
    adapter = LoxoneAdapter(real(tmp_path), httpx.MockTransport(lambda _: httpx.Response(200, text=body)))
    try:
        with pytest.raises(AdapterError):
            await adapter.snapshot()
    finally:
        await adapter.close()


async def test_ollama_rejects_invalid_advice(tmp_path):
    client = OllamaClient(config(tmp_path), httpx.MockTransport(lambda _: httpx.Response(200, json={"message": {"content": '{"command":"write_anything"}'}})))
    try:
        with pytest.raises(ValidationError):
            await client.reason(telemetry())
    finally:
        await client.close()
