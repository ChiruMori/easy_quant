from pydantic import BaseModel, Field


class InvitationCreateRequest(BaseModel):
    lifetime_hours: int = Field(default=168, ge=1, le=720)


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=20)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12)


class UserUpdateRequest(BaseModel):
    role: str | None = None
    status: str | None = None
