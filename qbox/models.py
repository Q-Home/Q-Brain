from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    control_id: str = Field(max_length=128)
    name: str = Field(max_length=128)
    state: str = Field(max_length=64)
    quantity: Literal["power", "stored_energy", "soc"]
    value: float
    unit: Literal["W", "Wh", "kWh", "%"]
    direction: Literal["unknown", "consumption"] = "unknown"


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    timestamp: float
    source: Literal["demo", "loxone"]
    observations: list[Observation] = Field(default_factory=list, max_length=100)
    grid_power: float | None = None  # W, positive import
    pv_power: float | None = Field(default=None, ge=0)
    battery_soc: float | None = Field(default=None, ge=0, le=100)
    battery_power: float | None = None  # W, positive charging
    ev_power: float | None = Field(default=None, ge=0)


class Advice(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    summary: str = Field(min_length=1, max_length=2000)
    suggested_ev_limit_w: int | None = Field(default=None, ge=0, le=22000)
    confidence: Literal["low", "medium", "high"]
    reasons: list[str] = Field(max_length=10)
