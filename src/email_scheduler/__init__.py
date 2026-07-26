"""email_scheduler — step 4 of the OpenClaw pipeline: email scheduling and dispatch."""
from email_scheduler.scheduler import dispatch_pending, schedule_for_deal

__all__ = ["schedule_for_deal", "dispatch_pending"]
