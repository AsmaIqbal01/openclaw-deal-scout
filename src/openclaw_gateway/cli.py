"""openclaw CLI — gateway status, dashboard, and doctor subcommands."""
from __future__ import annotations

import argparse
import asyncio
import sys
import webbrowser
from typing import Optional

from openclaw_gateway.config import load_gateway_config
from openclaw_gateway.tools.status import get_health

_SEP = "━" * 37


# ── helpers ────────────────────────────────────────────────────────────────────

def _format_uptime(seconds: Optional[int]) -> str:
    if seconds is None:
        return "unknown"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _format_doctor(report: dict) -> str:
    lines = ["OpenClaw Doctor — Health Check", _SEP]
    for c in report["components"]:
        icon = "✅" if c["status"] == "PASS" else "❌"
        name = c["name"]
        status = c["status"]
        if c["latency_ms"] is not None:
            tail = f"({c['latency_ms']}ms)"
        elif c["status"] == "PASS":
            tail = "(local)"
        else:
            tail = c["message"] or ""
        lines.append(f"  {icon}  {name:<16} {status:<6} {tail}")
    lines.append(_SEP)
    duration_s = report["duration_ms"] / 1000
    lines.append(f"Overall: {report['overall']}  ({duration_s:.1f}s)")
    return "\n".join(lines)


def _format_gateway_running(status: dict) -> str:
    uptime = _format_uptime(status.get("uptime_seconds"))
    last_run = status.get("last_cycle_at") or "never"
    cycle = "running" if status.get("cycle_running") else "idle"
    host = status.get("host", "?")
    port = status.get("port", "?")
    version = status.get("version", "?")
    return "\n".join([
        "OpenClaw Gateway: RUNNING",
        f"  Version : {version}",
        f"  Uptime  : {uptime}",
        f"  Host    : {host}:{port}",
        f"  Last run: {last_run}",
        f"  Cycle   : {cycle}",
    ])


# ── gateway status fetch ───────────────────────────────────────────────────────

async def _call_status_async(host: str, port: int) -> dict:
    from fastmcp import Client
    async with Client(f"http://{host}:{port}/mcp") as c:
        import json
        result = await c.call_tool("get_gateway_status", {})
        return json.loads(result.content[0].text)


def _fetch_gateway_status(host: str, port: int) -> Optional[dict]:
    """Return GatewayStatus dict from the running gateway, or None if unreachable."""
    try:
        return asyncio.run(_call_status_async(host, port))
    except Exception:
        return None


# ── subcommand handlers ────────────────────────────────────────────────────────

def _cmd_doctor(_args: argparse.Namespace) -> int:
    config = load_gateway_config()
    report = get_health(config)
    print(_format_doctor(report))
    return 0 if report["overall"] == "HEALTHY" else 1


def _cmd_gateway_status(_args: argparse.Namespace) -> int:
    config = load_gateway_config()
    status = _fetch_gateway_status(config.gateway_host, config.gateway_port)
    if status is None:
        print("OpenClaw Gateway: STOPPED")
        print(f"  Host    : {config.gateway_host}:{config.gateway_port}")
        return 1
    print(_format_gateway_running(status))
    return 0


def _cmd_dashboard(_args: argparse.Namespace) -> int:
    config = load_gateway_config()
    url = f"http://{config.gateway_host}:{config.gateway_port}"
    print(f"Opening OpenClaw dashboard at {url} ...")
    webbrowser.open(url)
    return 0


# ── entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(prog="openclaw", description="OpenClaw Deal Scout CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("doctor", help="Run health checks on all pipeline components")

    gw = sub.add_parser("gateway", help="Manage the OpenClaw gateway")
    gw_sub = gw.add_subparsers(dest="gateway_command")
    gw_sub.add_parser("status", help="Show gateway running status and uptime")

    sub.add_parser("dashboard", help="Open the OpenClaw dashboard in a browser")

    args = parser.parse_args()

    if args.command == "doctor":
        sys.exit(_cmd_doctor(args))
    elif args.command == "gateway" and getattr(args, "gateway_command", None) == "status":
        sys.exit(_cmd_gateway_status(args))
    elif args.command == "dashboard":
        sys.exit(_cmd_dashboard(args))
    else:
        parser.print_help()
        sys.exit(1)
