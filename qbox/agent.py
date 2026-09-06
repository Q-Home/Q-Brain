"""Periodic advisor uses the public MCP boundary; never calls write tools."""
import asyncio
from datetime import timedelta
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from .config import Settings
from .logging import event, setup_logging


async def cycle(c):
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {c.mcp_token.get_secret_value()}"},
                                 timeout=c.ollama_timeout_seconds + c.discovery_timeout_seconds + 30, trust_env=False) as http:
        async with streamable_http_client(c.mcp_url, http_client=http) as (read, write, _):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=c.ollama_timeout_seconds + c.discovery_timeout_seconds + 30)) as session:
                await session.initialize()
                result = await session.call_tool("analyze_energy", {})
                if result.isError:
                    raise RuntimeError("Analysis tool failed")
                event("agent_cycle_completed", executed=False)


async def main():
    setup_logging()
    c = Settings()
    while True:
        try:
            await cycle(c)
        except Exception:
            event("agent_cycle_failed")
        await asyncio.sleep(c.reasoning_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
