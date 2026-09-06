import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    loxberry_snapshot_path: str = ""
    demo_mode: bool = True
    observe_only: bool = True
    enable_ev_write: bool = False
    loxone_watchdog_confirmed: bool = False
    mcp_token: SecretStr = SecretStr("")
    mcp_url: str = "http://127.0.0.1:8080/mcp"
    mcp_allowed_hosts: list[str] = ["127.0.0.1:*", "localhost:*", "qbox:*"]
    loxone_url: str = "https://miniserver.local"
    loxone_username: str = ""
    loxone_password: SecretStr = SecretStr("")
    loxone_allow_http: bool = False
    loxone_grid_power: str = ""
    loxone_pv_power: str = ""
    loxone_battery_soc: str = ""
    loxone_battery_power: str = ""
    loxone_ev_power: str = ""
    loxone_ev_limit_input: str = ""
    ev_max_power_w: int = Field(11000, ge=0, le=22000)
    write_cooldown_seconds: float = Field(60, ge=1, le=3600)
    snapshot_max_age_seconds: float = Field(30, ge=1, le=300)
    request_timeout_seconds: float = Field(5, ge=1, le=30)
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3:4b"
    discovery_model: str = ""
    discovery_timeout_seconds: float = Field(300, ge=1, le=600)
    ollama_timeout_seconds: float = Field(120, ge=1, le=600)
    reasoning_interval_seconds: float = Field(300, ge=10, le=86400)
    history_path: Path = Path("/data/history.sqlite3")
    history_max_rows: int = Field(10000, ge=100, le=1000000)

    @model_validator(mode="after")
    def check_config(self):
        if len(self.mcp_token.get_secret_value()) < 32:
            raise ValueError("MCP_TOKEN must contain at least 32 characters")
        for name in ("loxone_url", "ollama_url", "mcp_url"):
            url = urlsplit(getattr(self, name))
            if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError(f"{name} must be an HTTP(S) URL without credentials/query/fragment")
        if self.loxberry_snapshot_path and (not self.observe_only or self.enable_ev_write or self.demo_mode):
            raise ValueError("LoxBerry telemetry requires real observe-only mode")
        if not self.demo_mode and not self.loxberry_snapshot_path:
            if not self.loxone_username or not self.loxone_password.get_secret_value():
                raise ValueError("Real mode requires Loxone credentials")
            if self.loxone_url.startswith("http:") and not self.loxone_allow_http:
                raise ValueError("HTTP Loxone requires explicit LOXONE_ALLOW_HTTP=true")
            if not all(self.read_mapping.values()):
                raise ValueError("Real mode requires all five Loxone read mappings")
        for value in [*self.read_mapping.values(), self.loxone_ev_limit_input]:
            if value and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
                raise ValueError("Loxone mappings must be simple input/output names or UUIDs")
        if self.enable_ev_write:
            if self.observe_only or self.demo_mode or not self.loxone_ev_limit_input or not self.loxone_watchdog_confirmed:
                raise ValueError("Writes require real mode, observe_only=false, mapped EV input and confirmed Loxone watchdog")
        return self

    @property
    def read_mapping(self):
        return {key: getattr(self, f"loxone_{key}") for key in
                ("grid_power", "pv_power", "battery_soc", "battery_power", "ev_power")}
