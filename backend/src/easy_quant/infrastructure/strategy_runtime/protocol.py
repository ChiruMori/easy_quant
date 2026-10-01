from pydantic import BaseModel, Field


class ChildRequest(BaseModel):
    source_code: str
    parameters: dict[str, object] = Field(default_factory=dict)
    context: dict[str, object] = Field(default_factory=dict)
    phase: str = "before_market"


class ChildResponse(BaseModel):
    ok: bool
    signals: list[dict[str, object]] = Field(default_factory=list)
    stdout: str = ""
    error: str | None = None
