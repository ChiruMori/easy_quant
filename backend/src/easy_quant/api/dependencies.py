from __future__ import annotations

from flask import current_app

from easy_quant.bootstrap import Container


def get_container() -> Container:
    return current_app.extensions["easy_quant_container"]
