from easy_quant.factors.context import FactorContext
from easy_quant.factors.registry import FactorRegistry


class FactorBridge:
    def __init__(self, registry: FactorRegistry, context: FactorContext) -> None:
        self.registry, self.context = registry, context

    def call(self, key: str, **parameters: object) -> object:
        return self.registry.call(key, self.context, parameters)
