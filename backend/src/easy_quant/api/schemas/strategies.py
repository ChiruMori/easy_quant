from pydantic import BaseModel, Field


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    source_code: str = Field(min_length=1, max_length=100_000)


class StrategyRunRequest(BaseModel):
    parameters: dict[str, object] = Field(default_factory=dict)
