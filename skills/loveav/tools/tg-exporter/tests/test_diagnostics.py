from telegram_exporter.diagnostics import friendly_error_message


class ApiIdInvalidError(Exception):
    pass


class PhoneCodeExpiredError(Exception):
    pass


class FloodWaitError(Exception):
    def __init__(self, seconds: int):
        super().__init__(f"wait {seconds}")
        self.seconds = seconds


def test_api_id_invalid_message_points_to_api_settings():
    text = friendly_error_message(ApiIdInvalidError("bad credentials"))
    assert "API ID / API Hash" in text
    assert "API 设置" in text
    assert "my.telegram.org" in text


def test_phone_code_expired_message_is_friendly():
    text = friendly_error_message(PhoneCodeExpiredError("expired"))
    assert "验证码" in text
    assert "过期" in text


def test_flood_wait_includes_seconds():
    text = friendly_error_message(FloodWaitError(42))
    assert "42" in text
    assert "Flood Wait" in text


def test_network_error_has_actionable_hint():
    text = friendly_error_message(ConnectionError("network unreachable"))
    assert "Telegram 官方客户端" in text
    assert "网络" in text
