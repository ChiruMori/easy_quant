from pathlib import Path

import pytest

from easy_quant.factors.ml.loader import load_weights


def test_model_weights_are_verified_and_inference_only() -> None:
    manifest = Path(__file__).parents[3] / "resources" / "models" / "manifest.json"
    weights = load_weights(manifest, "linear-return")
    assert weights["momentum"] == 0.25


def test_missing_model_fails() -> None:
    manifest = Path(__file__).parents[3] / "resources" / "models" / "manifest.json"
    with pytest.raises(KeyError):
        load_weights(manifest, "missing")
