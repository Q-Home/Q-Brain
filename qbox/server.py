import asyncio
import hmac
import time
from .discovery_ai import inventory, fingerprint
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field, StrictInt
from typing import Annotated
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .config import Settings
from .history import History
from .chat import ChatJobs
from .logging import event, setup_logging
from .loxone import LoxoneAdapter
from .discovery import LoxBerryAdapter
from .ollama import OllamaClient, analysis_failure
from .policy import EnergyService


def create_app(config=None):
    setup_logging()
    c = config or Settings()
    adapter = LoxBerryAdapter(c) if c.loxberry_snapshot_path else LoxoneAdapter(c)
    ollama = OllamaClient(c)
    history = History(c.history_path, c.history_max_rows)
    service = EnergyService(c, adapter, history)
    reason_lock = asyncio.Lock()
    chat_jobs = ChatJobs(c, adapter, ollama, reason_lock)
    mcp = FastMCP("Q-Box Energy", stateless_http=True, json_response=True,
                  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
                      allowed_hosts=c.mcp_allowed_hosts,
                      allowed_origins=["http://localhost:*", "http://127.0.0.1:*"]))

    @mcp.tool()
    async def get_energy_snapshot() -> dict:
        """Read known energy signals and per-device observations with explicit units; timestamp is Unix UTC."""
        try:
            return (await service.snapshot()).model_dump()
        except Exception:
            raise ValueError("Energy snapshot unavailable") from None

    @mcp.tool()
    async def discover_energy_signals() -> dict:
        """Read automatic signal discovery and ambiguity, without changing mappings."""
        if isinstance(adapter, LoxBerryAdapter):
            return await adapter.discovery()
        return {"mode": "demo" if c.demo_mode else "manual"}

    @mcp.tool()
    async def get_energy_history(limit: Annotated[int, Field(ge=1, le=100)] = 20) -> list[dict]:
        """Return recent local telemetry, decisions and write audit records."""
        return history.recent(limit)

    @mcp.tool()
    async def get_operating_mode() -> dict:
        """Read mode and configured physical limits."""
        return {"observe_only": c.observe_only, "demo_mode": c.demo_mode,
                "ev_write_enabled": c.enable_ev_write, "ev_max_power_w": c.ev_max_power_w}

    async def run_discovery():
        if not isinstance(adapter, LoxBerryAdapter):
            return None
        rows=inventory(adapter.document())
        key=fingerprint(rows,'compact-v2:' + (c.discovery_model or c.ollama_model))
        previous=history.latest('discovery')
        if previous and previous['payload'].get('fingerprint') == key and time.time()-previous['timestamp'] < 3600:
            return previous['payload']
        result=await ollama.discover(rows)
        record={**result,'fingerprint':key, 'model':c.discovery_model or c.ollama_model,
                'source':'loxone','executed':False}
        history.append('discovery',record)
        event('discovery_recorded',proposals=len(result['proposals']),executed=False)
        return record

    @mcp.tool()
    async def analyze_installation() -> dict:
        """Ask the local discovery model to inspect real control/state metadata, even without a complete snapshot."""
        if reason_lock.locked():
            raise ValueError('Analysis already running')
        async with reason_lock:
            return await run_discovery() or {'mode':'demo' if c.demo_mode else 'manual'}

    @mcp.tool()
    async def analyze_energy() -> dict:
        """Get structured local Ollama advice from fresh telemetry. Never executes advice."""
        if reason_lock.locked():
            raise ValueError("Analysis already running")
        async with reason_lock:
            try:
                discovery = None
                if isinstance(adapter, LoxBerryAdapter):
                    try:
                        discovery = await run_discovery()
                    except Exception as error:
                        failure = analysis_failure(error)
                        event('discovery_failed', code=failure['code'])
                        history.append('discovery_error', failure)
                try:
                    snapshot = await service.snapshot()
                except Exception:
                    if discovery is not None:
                        return {'kind':'discovery','discovery':discovery,'executed':False}
                    raise
                advice = await ollama.reason(snapshot)
                record = {"source": snapshot.source, "snapshot_timestamp": snapshot.timestamp,
                          "advice": advice.model_dump(), "executed": False}
                history.append("advice", record)
                event("advice_recorded", source=snapshot.source, executed=False)
                return record
            except Exception as error:
                failure = analysis_failure(error)
                history.append("analysis_error", failure)
                event("analysis_failed", code=failure["code"])
                raise ValueError("Analysis unavailable; check Loxone, Ollama and local storage") from None

    # Disabled write tools are absent from discovery, with policy checks as a second layer.
    if c.enable_ev_write:
        @mcp.tool()
        async def set_ev_power_limit(watts: Annotated[StrictInt, Field(ge=0, le=c.ev_max_power_w)]) -> dict:
            """Set the dedicated EV cap input in W. Zero stops charging. Loxone enforces watchdog/failsafes."""
            return await service.set_ev_limit(watts)

    async def health(request):
        return JSONResponse({"status": "ok"})

    async def ready(request):
        try:
            await adapter.snapshot()
            if not await ollama.ready():
                raise ValueError("Missing model")
            return JSONResponse({"status": "ready", "demo_mode": c.demo_mode})
        except Exception:
            return JSONResponse({"status": "not_ready"}, status_code=503)

    async def overview(request):
        # Cached local records only; never wait for Miniserver or model in the UI.
        result = {"history": history.recent(6), "discovery": {}, "installation_analysis": history.latest("discovery"), "discovery_error": history.latest("discovery_error"), "analysis_error": history.latest("analysis_error")}
        if isinstance(adapter, LoxBerryAdapter):
            try:
                result["discovery"] = await adapter.discovery()
            except Exception:
                result["discovery"] = {"error": "SDK-meetgegevens ontbreken of zijn verouderd."}
        return JSONResponse(result)

    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        event("started", observe_only=c.observe_only, demo_mode=c.demo_mode, ev_write_enabled=c.enable_ev_write)
        try:
            async with mcp.session_manager.run():
                yield
        finally:
            await chat_jobs.close()
            await adapter.close()
            await ollama.close()
            history.close()

    app = Starlette(routes=[Route("/chat", chat_jobs.endpoint, methods=["POST"]), Route("/healthz", health), Route("/readyz", ready), Route("/overview", overview), Mount("/", app=mcp_app)], lifespan=lifespan)
    return BearerAuth(app, c.mcp_token.get_secret_value())


class BearerAuth:
    def __init__(self, app, token):
        self.app, self.expected = app, f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] != "/healthz":
            headers = dict(scope["headers"])
            if not hmac.compare_digest(headers.get(b"authorization", b""), self.expected):
                await JSONResponse({"error": "unauthorized"}, 401)(scope, receive, send)
                return
        await self.app(scope, receive, send)
