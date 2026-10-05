from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from easy_quant.factors.context import FactorContext


class FactorFunction(Protocol):
    def __call__(self, context: FactorContext, parameters: dict[str, object]) -> object: ...


@dataclass(frozen=True, slots=True)
class FactorDefinition:
    key: str
    name: str
    description: str
    parameters: dict[str, str]
    output: str
    example: str
    output_example: str
    function: FactorFunction
