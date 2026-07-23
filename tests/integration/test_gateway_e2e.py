"""Gateway E2E integration test (T026).

Requires all pipeline env vars to be set and the full package installed.
Skipped by default — run with: pytest tests/integration/test_gateway_e2e.py -v
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

pytestmark = pytest.mark.skip(reason="E2E requires full pipeline env and running services")

_GATEWAY_PORT = 18790  # non-default port to avoid conflicts


@pytest.fixture
def gateway_proc(tmp_path):
    """Start the gateway subprocess and yield (proc, host, port)."""
    env = {
        **os.environ,
        "SCHEDULER_MODE": "gateway",
        "STATE_STORE_PATH": str(tmp_path / "state.json"),
        "PIPELINE_LOG_PATH": str(tmp_path / "pipeline.log"),
        "GATEWAY_PORT": str(_GATEWAY_PORT),
        "GATEWAY_HOST": "127.0.0.1",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "openclaw_gateway"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Poll until gateway is up (max 10 s)
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{_GATEWAY_PORT}/mcp/", timeout=1
            )
            break
        except (urllib.error.URLError, ConnectionRefusedError):
            time.sleep(0.25)
    else:
        proc.terminate()
        proc.wait(timeout=5)
        pytest.fail("Gateway did not start within 10 seconds")

    yield proc, "127.0.0.1", _GATEWAY_PORT

    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def test_gateway_status_returns_running(gateway_proc):
    import asyncio
    from fastmcp import Client

    proc, host, port = gateway_proc

    async def _call():
        import json
        async with Client(f"http://{host}:{port}/mcp/") as c:
            result = await c.call_tool("get_gateway_status", {})
            return json.loads(result[0].text)

    status = asyncio.run(_call())
    assert status["running"] is True
    assert isinstance(status["uptime_seconds"], int)
    assert status["uptime_seconds"] >= 0


def test_run_cycle_returns_pipeline_cycle(gateway_proc):
    import asyncio
    from fastmcp import Client

    proc, host, port = gateway_proc

    async def _call():
        import json
        async with Client(f"http://{host}:{port}/mcp/") as c:
            result = await c.call_tool("run_cycle", {})
            return json.loads(result[0].text)

    result = asyncio.run(_call())
    # Either a PipelineCycle dict or a busy response
    assert "emails_processed" in result or result.get("busy") is True


def test_get_pipeline_cycles_after_run(gateway_proc):
    import asyncio
    from fastmcp import Client

    proc, host, port = gateway_proc

    async def _call():
        import json
        async with Client(f"http://{host}:{port}/mcp/") as c:
            result = await c.call_tool("get_pipeline_cycles", {"limit": 1})
            return json.loads(result[0].text)

    result = asyncio.run(_call())
    assert "cycles" in result
    assert "total_in_log" in result


def test_sigterm_shuts_down_cleanly(gateway_proc):
    proc, host, port = gateway_proc
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pytest.fail("Gateway did not shut down within 5 seconds after SIGTERM")
    assert proc.returncode is not None
