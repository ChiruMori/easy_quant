from pydantic import BaseModel, Field


class CredentialsRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=1024)


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    status: str


def user_response(user) -> dict[str, str]:
    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role.value,
        status=user.status.value,
    ).model_dump()
