from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from easy_quant.platform_library.context import FactorContext


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
    defaults: Mapping[str, object] = field(default_factory=dict)
    datasets: tuple[str, ...] = ()
    integer_parameters: tuple[str, ...] = ()
    history_parameter: str | None = None
    history_extra: int = 0
    required_history: int | None = None
