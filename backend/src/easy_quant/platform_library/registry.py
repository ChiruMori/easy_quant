from easy_quant.domain.shared.errors import NotFoundError, ValidationError
from easy_quant.platform_library.context import FactorContext
from easy_quant.platform_library.types import FactorDefinition


class FactorRegistry:
    def __init__(self) -> None:
        self._items: dict[str, FactorDefinition] = {}

    def register(self, definition: FactorDefinition) -> None:
        if definition.key in self._items:
            raise ValidationError("因子重复注册", {"key": definition.key})
        if not all(
            (
                definition.description,
                definition.output,
                definition.example,
                definition.output_example,
            )
        ):
            raise ValidationError("因子文档不完整", {"key": definition.key})
        self._items[definition.key] = definition

    def list(self) -> tuple[FactorDefinition, ...]:
        return tuple(self._items.values())

    def get(self, key: str) -> FactorDefinition:
        try:
            return self._items[key]
        except KeyError as error:
            raise NotFoundError("factor") from error

    def call(self, key: str, context: FactorContext, parameters: dict[str, object]) -> object:
        definition = self.get(key)
        parameters = {**definition.defaults, **parameters}
        for name in definition.integer_parameters:
            if name in parameters:
                try:
                    value = int(str(parameters[name]))
                except ValueError as error:
                    raise ValidationError("因子窗口必须为整数") from error
                if not 1 <= value <= 2500:
                    raise ValidationError("因子窗口必须在 1–2500 之间")
                parameters[name] = value
        missing = definition.parameters.keys() - parameters.keys()
        if missing:
            raise ValidationError("缺少因子参数", {"fields": sorted(missing)})
        return definition.function(context, parameters)
