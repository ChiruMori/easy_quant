from pydantic import BaseModel


class FactorDocument(BaseModel):
    key: str
    name: str
    description: str
    parameters: dict[str, str]
    output: str
    example: str
