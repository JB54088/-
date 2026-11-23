from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str
    remember_me: bool = False


class UserBrief(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    department_id: int | None = None
    department_name: str | None = None


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(max_length=80)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("姓名不能为空")
        if len(normalized) > 80:
            raise ValueError("姓名不能超过80个字符")
        return normalized


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserBrief


class DepartmentBrief(BaseModel):
    id: int
    name: str
