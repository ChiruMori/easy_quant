from urllib.parse import parse_qs, urlsplit

from easy_quant.domain.notifications.entities import ChannelType
from easy_quant.domain.shared.errors import ValidationError

BOT_CHANNELS = {"dingtalk", "feishu", "wecom"}


def validate_notification_target(channel, destination, signing_secret=""):
    if not isinstance(channel, str) or channel not in {item.value for item in ChannelType}:
        raise ValidationError("不支持的通知渠道")
    if not isinstance(destination, str) or not destination.strip() or len(destination) > 4096:
        raise ValidationError("请填写有效通知目标（最多 4096 字）")
    if not isinstance(signing_secret, str) or len(signing_secret) > 512:
        raise ValidationError("签名密钥格式无效（最多 512 字）")
    if signing_secret and channel not in {"dingtalk", "feishu"}:
        raise ValidationError("该渠道不支持签名密钥")
    if channel not in BOT_CHANNELS:
        return
    try:
        url = urlsplit(destination.strip())
        valid = url.scheme == "https" and not url.username and not url.password and not url.fragment
        valid = valid and url.port in {None, 443}
        query = parse_qs(url.query)
        if channel == "dingtalk":
            valid = valid and url.hostname == "oapi.dingtalk.com" and url.path == "/robot/send"
            valid = valid and set(query) == {"access_token"} and len(query["access_token"]) == 1
        elif channel == "wecom":
            valid = (
                valid
                and url.hostname == "qyapi.weixin.qq.com"
                and url.path == "/cgi-bin/webhook/send"
            )
            valid = valid and set(query) == {"key"} and len(query["key"]) == 1
        else:
            valid = valid and url.hostname == "open.feishu.cn" and not url.query
            prefix = "/open-apis/bot/v2/hook/"
            valid = valid and url.path.startswith(prefix) and bool(url.path[len(prefix) :])
            valid = valid and "/" not in url.path[len(prefix) :]
    except ValueError:
        valid = False
    if not valid:
        raise ValidationError("请填写该平台完整的 HTTPS 群机器人 Webhook 地址，不附加临时签名参数")
