from pydantic import BaseModel, Field


class AcquisitionRequest(BaseModel):
    dataset_key: str = Field(min_length=1, max_length=80)
    parameters: dict[str, object] = Field(default_factory=dict)
    symbols: list[str] = Field(default_factory=list)
    start_day: str | None = None
    end_day: str | None = None
    force: bool = False


class SourceOrderRequest(BaseModel):
    source_keys: list[str] = Field(min_length=1)
    enabled_keys: list[str] = Field(default_factory=list)
