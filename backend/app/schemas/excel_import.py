from pydantic import BaseModel, Field


class ExcelImportBindRequest(BaseModel):
    customer_id: int
    note: str | None = Field(default=None, max_length=2000)


class ExcelImportIgnoreRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
