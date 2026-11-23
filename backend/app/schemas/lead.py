from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from .common import SourceCategory, SourceLevel1, SourceLevel2


class LeadCreate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    phone: str | None = Field(default=None, min_length=5, max_length=30)
    wechat_id: str | None = Field(default=None, max_length=80)
    gender: str | None = Field(default=None, max_length=10)
    source_note: str | None = Field(default=None, max_length=500, validation_alias=AliasChoices("source_note", "source"))
    notes: str | None = Field(default=None, max_length=2000)
    # These fields are accepted by the shared lead endpoint for administrator
    # creation.  The router enforces that only admins may use them.
    source_level_1: SourceLevel1 | None = None
    source_level_2: SourceLevel2 | None = None
    source_custom_name: str | None = Field(default=None, max_length=120)
    tag_ids: list[int] = Field(default_factory=list, max_length=20)
    assigned_to: int | None = None
    submission_id: str | None = Field(default=None, max_length=100, validation_alias=AliasChoices("submission_id", "idempotency_key"))

    @field_validator("name", "phone", mode="before")
    @classmethod
    def empty_identity_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def require_name_or_phone(self):
        if not (self.name and self.name.strip()) and not (self.phone and self.phone.strip()):
            raise ValueError("客户姓名和手机号至少填写一项")
        return self


class LeadReviewRequest(BaseModel):
    action: Literal["approve", "reject"] = "approve"
    source_category: SourceCategory | None = None
    source_level_1: SourceLevel1 | None = None
    source_level_2: SourceLevel2 | None = None
    source_custom_name: str | None = Field(default=None, max_length=120)
    tag_ids: list[int] = Field(default_factory=list, max_length=20)
    assigned_to: int | None = None
    review_note: str | None = Field(default=None, max_length=2000)


class DuplicateLeadReviewRequest(BaseModel):
    action: Literal["confirm_duplicate", "not_duplicate", "reject"]
    review_note: str | None = Field(default=None, max_length=2000)


class LeadListItem(BaseModel):
    id: int
    name: str
    phone: str | None = None
    wechat_id: str | None = None
    gender: str | None = None
    source_category: SourceCategory | None = None
    source_level_1: SourceLevel1 | None = None
    source_level_2: SourceLevel2 | None = None
    source_custom_name: str | None = None
    source_note: str | None = None
    notes: str | None = None
    reported_by_name: str | None = None
    reported_at: datetime | None = None
    assigned_to_name: str | None = None
    lead_status: str
    tags: list[str] = Field(default_factory=list)
    total_spend: Decimal = Decimal("0")
    order_count: int = 0
