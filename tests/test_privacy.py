"""M0-2 敏感检测规则的回归测试。

规则改动必须同步更新本文件，见 ``privacy/data_class.md`` 第 7 节。
"""

from snowfoxclaw.privacy.patterns import Sensitivity, max_sensitivity, redact, scan

VALID_ID_CARD = "110101199003071233"
INVALID_ID_CARD = "110101199003071234"
VALID_CARD = "4111111111111111"


def kinds(text: str) -> list[str]:
    return [f.kind for f in scan(text)]


def test_plain_text_has_no_finding():
    assert scan("帮我整理下周的日程安排。") == []
    assert max_sensitivity("帮我整理下周的日程安排。") == Sensitivity.LOW


def test_phone_detected():
    assert kinds("我手机号 13812345678，随时联系") == ["phone"]


def test_id_card_requires_valid_checksum():
    assert kinds(f"证件号 {VALID_ID_CARD}") == ["id_card"]
    assert "id_card" not in kinds(f"证件号 {INVALID_ID_CARD}")


def test_bank_card_requires_luhn():
    assert kinds(f"卡号 {VALID_CARD}") == ["bank_card"]
    assert "bank_card" not in kinds("订单号 1234567890123456")


def test_password_detected():
    assert kinds("我的密码是 abc12345") == ["password"]


def test_api_key_detected():
    assert kinds("key: sk-abcdefghijklmnop") == ["api_key"]


def test_email_is_medium():
    findings = scan("发我邮箱 a@b.com")
    assert [f.kind for f in findings] == ["email"]
    assert findings[0].sensitivity == Sensitivity.MEDIUM


def test_max_sensitivity_picks_highest():
    assert max_sensitivity("邮箱 a@b.com 和手机 13812345678") == Sensitivity.HIGH


def test_redact_removes_secret_and_keeps_kind():
    out = redact("手机 13812345678，邮箱 a@b.com")
    assert "13812345678" not in out
    assert "a@b.com" not in out
    assert "[REDACTED:phone]" in out
    assert "[REDACTED:email]" in out


def test_redact_keeps_text_without_secret():
    text = "帮我把日程挪到周四。"
    assert redact(text) == text


def test_overlapping_rules_keep_one_finding():
    findings = scan(VALID_ID_CARD)
    assert [f.kind for f in findings] == ["id_card"]
    assert (findings[0].start, findings[0].end) == (0, len(VALID_ID_CARD))


def test_empty_input():
    assert scan("") == []
    assert redact("") == ""
