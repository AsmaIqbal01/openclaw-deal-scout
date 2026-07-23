"""GatewayConfig — extends PipelineConfig with gateway-specific env vars."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from pipeline_orchestrator.config import PipelineConfig, load_config


@dataclass
class GatewayConfig(PipelineConfig):
    gateway_host: str
    gateway_port: int


def load_gateway_config() -> GatewayConfig:
    """Read and validate all env vars for the gateway.

    Calls pipeline_orchestrator.config.load_config() for the base fields,
    then reads GATEWAY_HOST and GATEWAY_PORT. Exits on any validation error.
    """
    base = load_config()

    gateway_host = os.environ.get("GATEWAY_HOST", "127.0.0.1").strip() or "127.0.0.1"

    gateway_port_raw = os.environ.get("GATEWAY_PORT", "18789").strip()
    try:
        gateway_port = int(gateway_port_raw)
    except ValueError:
        sys.exit(
            f"[openclaw_gateway] ERROR: GATEWAY_PORT={gateway_port_raw!r} is not a valid integer"
        )
    if not (1 <= gateway_port <= 65535):
        sys.exit(
            f"[openclaw_gateway] ERROR: GATEWAY_PORT={gateway_port} is out of range 1–65535"
        )

    return GatewayConfig(
        **vars(base),
        gateway_host=gateway_host,
        gateway_port=gateway_port,
    )
