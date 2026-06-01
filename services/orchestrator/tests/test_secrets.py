import pytest

from die_firma.secrets import SecretError, check_anthropic_key, check_token

GOOD = "Xk7_3sdf92kfjs03ksdf-aiwe9382"


def test_check_token_failures():
    with pytest.raises(SecretError, match="missing"):
        check_token(None)
    with pytest.raises(SecretError, match="missing"):
        check_token("   ")
    with pytest.raises(SecretError, match="too short"):
        check_token("Ab1-xy")
    with pytest.raises(SecretError, match="placeholder"):
        check_token("THIS-IS-A-CHANGEME-TOKEN-123456")
    with pytest.raises(SecretError, match="character variety"):
        check_token("a" * 30)


def test_check_token_ok_trims():
    assert check_token(f"  {GOOD}  ") == GOOD


def test_check_anthropic_key():
    with pytest.raises(SecretError, match="missing"):
        check_anthropic_key(None)
    with pytest.raises(SecretError, match="sk-ant-"):
        check_anthropic_key("nope-1234567890123456789012345")
    with pytest.raises(SecretError, match="placeholder"):
        check_anthropic_key("sk-ant-REPLACE-WITH-REAL-KEY")
    with pytest.raises(SecretError, match="too short"):
        check_anthropic_key("sk-ant-x")
    assert (
        check_anthropic_key("sk-ant-abc123def456ghi789jkl012") == "sk-ant-abc123def456ghi789jkl012"
    )
