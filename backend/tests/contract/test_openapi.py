import json
from pathlib import Path

from easy_quant.api.app import create_app
from tests.fakes.platform import make_test_container, make_test_settings


def test_openapi_covers_every_public_route() -> None:
    document = json.loads((Path(__file__).parents[2] / "openapi.yaml").read_text(encoding="utf-8"))
    assert document["openapi"].startswith("3.1")
    documented = set(document["paths"])
    settings = make_test_settings()
    app = create_app(settings=settings, container=make_test_container(settings))
    actual = {
        rule.rule.removeprefix("/api/v1").replace("<", "{").replace(">", "}")
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/v1")
    }
    assert actual <= documented
    operation_ids = [
        operation["operationId"]
        for path in document["paths"].values()
        for method, operation in path.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(operation_ids) == len(set(operation_ids))
