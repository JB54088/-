from pydantic import BaseModel, ConfigDict, Field


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str = Field(default="blue", max_length=20)


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    color: str | None = Field(default=None, max_length=20)


class CustomerTagsRequest(BaseModel):
    tag_ids: list[int] = Field(default_factory=list, max_length=20)


class TagResponse(BaseModel):
    id: int
    name: str
    color: str
    customer_count: int = 0

    model_config = ConfigDict(from_attributes=True)
