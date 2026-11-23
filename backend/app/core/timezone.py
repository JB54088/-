"""Application clock helpers.

Lead timestamps are stored as timezone-aware UTC instants.  Presentation
belongs to the client, which formats them in the business timezone.
"""

from datetime import datetime, timezone


BUSINESS_TIMEZONE = "Asia/Shanghai"


def utc_now() -> datetime:
    """Return the current server instant as an aware UTC datetime."""

    # Keep sub-second precision so a rapid report/approval sequence still
    # preserves the true event order.
    return datetime.now(timezone.utc)
