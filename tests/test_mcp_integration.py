"""Real HTTP MCP initialize/discovery/tool cycle; only Ollama is a local fixture."""
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from qbox.agent import cycle
from qbox.config import Settings

TOKEN = "integration-token-012345678901234567890"


class OllamaFixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        if self.path.startswith("/dev/sps/io/"):
            self.wfile.write(b'<LL value="42" Code="200"/>')
        else:
            self.wfile.write(json.dumps({"models": [{"name": "qwen3:4b"}]}).encode())

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.path == "/api/chat"
        assert data["stream"] is False and "properties" in data["format"]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"message": {"content": json.dumps({"summary": "Demo observation", "confidence": "low", "reasons": ["No forecast supplied"], "suggested_ev_limit_w": 1000})}}).encode())


@pytest.fixture(params=[False, True], ids=["observe", "controlled-write"])
def running_service(tmp_path, request):
    mock = ThreadingHTTPServer(("127.0.0.1", 0), OllamaFixture)
    thread = threading.Thread(target=mock.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "MCP_TOKEN": TOKEN, "DEMO_MODE": "true", "OBSERVE_ONLY": "true", "ENABLE_EV_WRITE": "false",
           "HISTORY_PATH": str(tmp_path / "history.sqlite3"), "OLLAMA_URL": f"http://127.0.0.1:{mock.server_port}"}
    if request.param:
        env.update(DEMO_MODE="false", OBSERVE_ONLY="false", ENABLE_EV_WRITE="true", LOXONE_WATCHDOG_CONFIRMED="true",
                   LOXONE_URL=f"http://127.0.0.1:{mock.server_port}", LOXONE_ALLOW_HTTP="true",
                   LOXONE_USERNAME="test", LOXONE_PASSWORD="secret", LOXONE_EV_LIMIT_INPUT="EVCap")
        env.update({f"LOXONE_{key}": key for key in ["GRID_POWER", "PV_POWER", "BATTERY_SOC", "BATTERY_POWER", "EV_POWER"]})
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "qbox.server:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port), "--no-access-log"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                if httpx.get(url + "/healthz", trust_env=False).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None:
                pytest.fail("Service exited at startup")
            time.sleep(0.1)
        else:
            pytest.fail("Service startup timed out")
        yield url, request.param
    finally:
        process.terminate()
        process.wait(timeout=10)
        mock.shutdown()
        mock.server_close()
        thread.join(timeout=5)


async def test_full_mcp_cycle(running_service):
    url, writes = running_service
    async with httpx.AsyncClient(trust_env=False) as client:
        assert (await client.get(url + "/readyz")).status_code == 401
        assert (await client.post(url + "/mcp", json={})).status_code == 401
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}, trust_env=False) as client:
        assert (await client.get(url + "/readyz")).status_code == 200
        async with streamable_http_client(url + "/mcp", http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                expected = {"get_energy_snapshot", "get_energy_history", "get_operating_mode", "analyze_energy"}
                assert names == expected | ({"set_ev_power_limit"} if writes else set())
                snap = await session.call_tool("get_energy_snapshot", {})
                assert not snap.isError and json.loads(snap.content[0].text)["source"] == ("loxone" if writes else "demo")
                advice = await session.call_tool("analyze_energy", {})
                assert not advice.isError and json.loads(advice.content[0].text)["executed"] is False
                invalid = await session.call_tool("get_energy_history", {"limit": 10000})
                assert invalid.isError
                history = await session.call_tool("get_energy_history", {"limit": 10})
                assert not history.isError
                if writes:
                    invalid = await session.call_tool("set_ev_power_limit", {"watts": 11001})
                    assert invalid.isError
                    accepted = await session.call_tool("set_ev_power_limit", {"watts": 1000})
                    assert not accepted.isError
                    assert json.loads(accepted.content[0].text)["status"] == "accepted_by_loxone"
                else:
                    forbidden = await session.call_tool("set_ev_power_limit", {"watts": 1000})
                    assert forbidden.isError
    await cycle(Settings(_env_file=None, mcp_token=TOKEN, mcp_url=url + "/mcp"))
