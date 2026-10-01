import pytest

from easy_quant.application.services.strategy_validation import PythonStrategyValidator
from easy_quant.domain.shared.errors import ValidationError


def test_valid_template_contract() -> None:
    PythonStrategyValidator().validate(
        "def before_market(context, parameters):\n    return []\n"
        "def on_market(context, parameters):\n    return []\n"
        "def after_market(context, parameters):\n    return []\n"
    )


def test_import_and_invalid_entry_are_rejected() -> None:
    with pytest.raises(ValidationError):
        PythonStrategyValidator().validate(
            "import os\n"
            "def before_market(context, parameters):\n return []\n"
            "def on_market(context, parameters):\n return []\n"
            "def after_market(context, parameters):\n return []"
        )
    with pytest.raises(ValidationError):
        PythonStrategyValidator().validate("def other():\n return []")


def test_legacy_single_entry_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PythonStrategyValidator().validate("def strategy(context, parameters):\n return []")
