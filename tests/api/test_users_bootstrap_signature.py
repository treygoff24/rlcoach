"""Tests for bootstrap signature verification."""

from rlcoach.api.routers.users import BootstrapRequest, _verify_bootstrap_signature


def test_verify_bootstrap_signature_without_secret(monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_SECRET", raising=False)
    request = BootstrapRequest(
        provider="google",
        provider_account_id="acct-1",
        email="u@example.com",
        name=None,
        image=None,
    )
    assert _verify_bootstrap_signature(request, signature=None) is True


def test_verify_bootstrap_signature_with_secret(monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_SECRET", "abc123")
    request = BootstrapRequest(
        provider="steam",
        provider_account_id="steam-1",
        email="x@example.com",
        name=None,
        image=None,
    )
    payload = "steam:steam-1:x@example.com"

    import hashlib
    import hmac

    valid = hmac.new(b"abc123", payload.encode(), hashlib.sha256).hexdigest()
    assert _verify_bootstrap_signature(request, valid) is True
    assert _verify_bootstrap_signature(request, "bad") is False
    assert _verify_bootstrap_signature(request, None) is False
