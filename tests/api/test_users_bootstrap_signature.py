"""Tests for bootstrap signature verification."""

from rlcoach.api.routers.users import BootstrapRequest, _verify_bootstrap_signature


def test_verify_bootstrap_signature_empty_secret_in_production(monkeypatch):
    """Empty-string BOOTSTRAP_SECRET is indistinguishable from absent — must reject in production."""
    monkeypatch.setenv("BOOTSTRAP_SECRET", "")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SAAS_MODE", raising=False)
    request = BootstrapRequest(
        provider="google",
        provider_account_id="acct-prod",
        email="prod@example.com",
        name=None,
        image=None,
    )
    # Empty string is falsy — same rejection path as absent secret in production
    assert _verify_bootstrap_signature(request, signature=None) is False


def test_verify_bootstrap_signature_without_secret_in_development(monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("SAAS_MODE", raising=False)
    request = BootstrapRequest(
        provider="google",
        provider_account_id="acct-1",
        email="u@example.com",
        name=None,
        image=None,
    )
    # No secret in dev → allowed (with warning)
    assert _verify_bootstrap_signature(request, signature=None) is True


def test_verify_bootstrap_signature_without_secret_in_production(monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    request = BootstrapRequest(
        provider="google",
        provider_account_id="acct-1",
        email="u@example.com",
        name=None,
        image=None,
    )
    # No secret in production → rejected
    assert _verify_bootstrap_signature(request, signature=None) is False


def test_verify_bootstrap_signature_without_secret_in_saas_mode(monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SAAS_MODE", "true")
    request = BootstrapRequest(
        provider="google",
        provider_account_id="acct-1",
        email="u@example.com",
        name=None,
        image=None,
    )
    # SAAS_MODE=true counts as production even if ENVIRONMENT is not set
    assert _verify_bootstrap_signature(request, signature=None) is False


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
