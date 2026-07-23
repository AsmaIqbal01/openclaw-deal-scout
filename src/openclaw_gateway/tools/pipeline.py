"""Pipeline MCP tools — US3 readers (T021–T023) and US4 run_cycle (T027)."""
from __future__ import annotations


def run_cycle() -> dict:
    """Trigger one pipeline cycle and return a PipelineCycle dict.

    Returns {"busy": True, ...} if a cycle is already running.
    Updates server._last_cycle_at and server._cycle_running.
    """
    import openclaw_gateway.server as _srv
    import pipeline_orchestrator.runner as _runner
    from datetime import datetime, timezone
    from pipeline_orchestrator.cycle_logger import CycleLogger
    from pipeline_orchestrator.lock import CycleLockActiveError

    config = _srv._config
    captured: dict = {}

    class _CapturingLogger(CycleLogger):
        def emit_cycle_summary(
            self, *, ts, emails_processed, crm_logged, notified, pending, errors
        ):
            super().emit_cycle_summary(
                ts=ts, emails_processed=emails_processed, crm_logged=crm_logged,
                notified=notified, pending=pending, errors=errors,
            )
            captured.update(
                ts=ts, emails_processed=emails_processed, crm_logged=crm_logged,
                notified=notified, pending=pending, errors=errors,
            )

    cycle_logger = _CapturingLogger(config)
    _srv._cycle_running = True
    try:
        _runner.run_cycle(config, cycle_logger)
        _srv._last_cycle_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return captured
    except CycleLockActiveError:
        return {
            "busy": True,
            "message": "A pipeline cycle is already running. Try again after it completes.",
        }
    except Exception as exc:
        return {
            "error": str(exc),
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    finally:
        _srv._cycle_running = False


def get_pipeline_cycles(limit: int = 20) -> dict:
    """Return the most-recent *limit* pipeline cycle summaries from pipeline.log."""
    import openclaw_gateway.server as _srv
    from openclaw_gateway import readers

    config = _srv._config
    cycles = readers.read_pipeline_log(limit, config)
    total = len(readers.read_pipeline_log(99_999, config))
    return {"cycles": cycles, "total_in_log": total}


def get_deals(limit: int = 50, status: str = "all") -> dict:
    """Return up to *limit* DealRecord dicts from the state store."""
    import openclaw_gateway.server as _srv
    from openclaw_gateway import readers

    config = _srv._config
    deals = readers.read_deals(limit, status, config)
    total = len(readers.read_deals(999_999, "all", config))
    return {"deals": deals, "total_deals": total, "filtered_by": status}


def get_quota_usage() -> dict:
    """Return estimated Gemini quota usage for the current UTC calendar day."""
    import openclaw_gateway.server as _srv
    from openclaw_gateway import readers

    return readers.compute_quota_usage(_srv._config)
