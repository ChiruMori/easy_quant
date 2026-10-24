import httpx
import pytest

from easy_quant.infrastructure.notifications.bot_webhooks import BotWebhookChannel
from tests.api.test_run_context import setup
from tests.contract.notifications.test_bot_webhooks import URLS


@pytest.mark.parametrize("kind", ["dingtalk", "feishu", "wecom"])
def test_robot_credentials_edit_test_delivery_and_private_responses(kind):
    c, client, headers, _ = setup()
    sent = []

    def send(request):
        sent.append(request)
        return httpx.Response(200, json={"code": 0} if kind == "feishu" else {"errcode": 0})

    c.notification_channels[kind] = BotWebhookChannel(
        httpx.Client(transport=httpx.MockTransport(send)), c.authentication.clock
    )
    secret = "fixture-signature" if kind != "wecom" else ""
    result = client.post(
        "/api/v1/notifications/subscriptions",
        headers=headers,
        json={
            "name": "测试机器人",
            "channel": kind,
            "destination": URLS[kind],
            "signing_secret": secret,
        },
    )
    assert result.status_code == 201
    item = result.get_json()["data"]
    assert item["destination"] == "***" and "signing_secret" not in item
    stored = next(row for row in c.state.subscriptions if row["id"] == item["id"])
    assert URLS[kind] not in stored["destination_encrypted"]
    if secret:
        assert secret not in stored["signing_secret_encrypted"]
    path = f"/api/v1/notifications/subscriptions/{item['id']}"
    detail = client.get(path)
    assert detail.headers["Cache-Control"] == "no-store"
    assert detail.get_json()["data"]["signing_secret"] == secret
    assert client.patch(path, headers=headers, json={"enabled": False}).status_code == 200
    assert (
        client.patch(
            path, headers=headers, json={"destination": URLS[kind], "signing_secret": ""}
        ).status_code
        == 200
    )
    assert client.get(path).get_json()["data"]["enabled"] is False
    assert client.get(path).get_json()["data"]["signing_secret"] == ""
    assert client.post(path + "/test", headers=headers).status_code == 400
    client.patch(path, headers=headers, json={"enabled": True})
    assert client.post(path + "/test", headers=headers).get_json()["data"]["status"] == "delivered"
    assert len(sent) == 1
    for row in c.state.subscriptions:
        if row["id"] == item["id"]:
            row["owner_id"] = "other"
    assert client.get(path).status_code == 404
