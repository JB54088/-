from datetime import datetime

from pydantic import BaseModel


class ReportResponse(BaseModel):
    period_type: str
    period_start: datetime
    period_end: datetime
    metrics: dict
    ai_summary: str
