from __future__ import annotations


def friendly_error_message(exc: Exception) -> str:
    name = type(exc).__name__
    message = str(exc).strip()

    if name == "SessionBusyError":
        return (
            "Telegram Session 正在被另一个 TG Exporter/tgctl 进程使用。"
            "请关闭另一个 TG Exporter 窗口，或等待正在执行的 tgctl 命令结束后重试。"
        )
    if name in {"ApiIdInvalidError", "ApiIdInvalid"}:
        return "API ID / API Hash 无效或不匹配。请打开『API 设置』，从 my.telegram.org → API development tools 重新复制你自己的 api_id 和 api_hash。"
    if name == "ApiIdPublishedFloodError":
        return "这个 API ID 已被 Telegram 判定为公开泄露，当前不能继续使用。请不要把 API Hash 放进 GitHub、截图或日志。"
    if name == "PhoneNumberInvalidError":
        return "手机号格式无效。请使用国际格式，例如中国大陆号码填写为 +86xxxxxxxxxxx。"
    if name in {"PhoneNumberBannedError", "UserDeactivatedBanError"}:
        return "Telegram 拒绝了这个账号/手机号的登录请求，账号可能处于限制或封禁状态。"
    if name in {"PhoneNumberFloodError", "PhonePasswordFloodError"}:
        return "登录尝试过于频繁，Telegram 暂时限制了继续尝试。请停止重复请求验证码，稍后再试。"
    if name == "PhoneCodeInvalidError":
        return "验证码不正确。请使用 Telegram 官方客户端最新收到的登录验证码。"
    if name == "PhoneCodeExpiredError":
        return "验证码已经过期，请重新发起登录并使用新的验证码。"
    if name == "PasswordHashInvalidError":
        return "两步验证密码不正确。"
    if name == "FloodWaitError":
        seconds = getattr(exc, "seconds", None)
        if seconds:
            return f"Telegram 要求等待 {seconds} 秒后再试（Flood Wait）。"
        return "Telegram 触发了 Flood Wait，请稍后再试。"
    if name in {"AuthKeyUnregisteredError", "AuthKeyInvalidError", "AuthKeyDuplicatedError"}:
        return "本地 Telegram Session 已失效或冲突。请点击『重置登录』清除本地 Session 后重新登录。"
    if name in {"OperationalError", "DatabaseError"} and "locked" in message.lower():
        return "Telegram Session 文件被占用。请确认没有同时打开多个本程序实例，然后重试。"
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return "无法连接 Telegram 网络。请先确认 Telegram 官方客户端在这台电脑当前网络下可以正常连接；如使用代理/VPN，也要确保本程序能访问 Telegram。"
    if name in {"RPCError", "ServerError"}:
        return f"Telegram API 返回错误：{message or name}"

    if message:
        return f"{name}: {message}"
    return name
