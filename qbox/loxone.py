import asyncio
import math
import time
from defusedxml import ElementTree
import httpx

from .config import Settings
from .models import Snapshot


class AdapterError(Exception):
    """Sanitized upstream failure: no credentials or raw response body."""


class LoxoneAdapter:
    def __init__(self, config: Settings, transport=None):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.loxone_url.rstrip("/") + "/",
            auth=(config.loxone_username, config.loxone_password.get_secret_value()),
            timeout=config.request_timeout_seconds, follow_redirects=False,
            transport=transport, trust_env=False,
        )

    async def close(self):
        await self.client.aclose()

    async def _io(self, control: str, value: str) -> str:
        try:
            # Only validated configuration supplies control; no arbitrary command tool.
            response = await self.client.get(f"dev/sps/io/{control}/{value}")
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
            if root.tag != "LL" or root.attrib.get("Code", root.attrib.get("code")) != "200":
                raise ValueError("Loxone rejected request")
            return root.attrib["value"]
        except Exception as exc:
            raise AdapterError("Loxone request failed or returned invalid data") from None

    async def snapshot(self) -> Snapshot:
        started = time.time()
        if self.config.demo_mode:
            return Snapshot(timestamp=started, source="demo", grid_power=1250,
                            pv_power=3400, battery_soc=62, battery_power=800, ev_power=1800)
        try:
            keys = list(self.config.read_mapping)
            values = await asyncio.gather(*(self._io(self.config.read_mapping[k], "state") for k in keys))
            parsed = {key: float(value) for key, value in zip(keys, values)}
            if not all(math.isfinite(x) for x in parsed.values()):
                raise ValueError("Non-finite telemetry")
            return Snapshot(timestamp=started, source="loxone", **parsed)
        except Exception:
            raise AdapterError("Incomplete or invalid Loxone snapshot") from None

    async def set_ev_limit(self, watts: int):
        # Defense in depth for direct callers; policy adds freshness/cooldown checks.
        c = self.config
        if c.observe_only or c.demo_mode or not c.enable_ev_write or not c.loxone_watchdog_confirmed:
            raise AdapterError("Writes disabled")
        if type(watts) is not int or not 0 <= watts <= c.ev_max_power_w:
            raise AdapterError("EV limit outside configured range")
        await self._io(c.loxone_ev_limit_input, str(watts))
