import asyncio
import time
from .logging import event


class PolicyError(Exception):
    pass


class EnergyService:
    """Extension point for deterministic constraints; AI output never executes here."""
    def __init__(self, config, adapter, history):
        self.config, self.adapter, self.history = config, adapter, history
        self.lock = asyncio.Lock()
        self.last_attempt = -float("inf")

    async def snapshot(self):
        data = await self.adapter.snapshot()
        self.history.append("snapshot", data.model_dump())
        return data

    async def set_ev_limit(self, watts: int):
        async with self.lock:
            c = self.config
            try:
                if c.observe_only or c.demo_mode or not c.enable_ev_write:
                    raise PolicyError("Writes disabled by configuration")
                if type(watts) is not int or not 0 <= watts <= c.ev_max_power_w:
                    raise PolicyError("EV limit outside configured range")
                if time.monotonic() - self.last_attempt < c.write_cooldown_seconds:
                    raise PolicyError("Write cooldown active")
                snapshot = await self.adapter.snapshot()
                age = time.time() - snapshot.timestamp
                if snapshot.source != "loxone" or not 0 <= age <= c.snapshot_max_age_seconds:
                    raise PolicyError("Fresh real telemetry required")
                # Audit must succeed before IO. An uncertain write is never retried automatically.
                self.history.append("ev_write_attempt", {"watts": watts})
                self.last_attempt = time.monotonic()
                await self.adapter.set_ev_limit(watts)
            except Exception:
                event("ev_write_rejected_or_failed")
                raise PolicyError("EV write rejected or failed; inspect configuration and installation before retrying") from None
            self.history.append("ev_write_accepted", {"watts": watts})
            event("ev_write_accepted", watts=watts)
            return {"status": "accepted_by_loxone", "watts": watts, "physical_state_verified": False}
