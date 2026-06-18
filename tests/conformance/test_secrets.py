"""R14 secrets-chain conformance (src/pipyer/secrets.py, graduated from the spike).

No real `op` calls: the 1Password leg is exercised through subprocess and PATH
mocking. The contract: provider chain auto/1password/env, (secret, provider)
return so provenance is reportable, exhaustion names everything that was tried.
"""

import pytest

import pipyer.secrets as secrets_mod
from pipyer.secrets import SecretResolutionError, resolve_secret


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    secrets_mod.clear_cache()
    monkeypatch.delenv("PIPYER_SECRET_PROVIDER", raising=False)
    monkeypatch.delenv("PIPYER_TESTKEY_OP_REFERENCE", raising=False)
    monkeypatch.delenv("TESTKEY", raising=False)
    yield
    secrets_mod.clear_cache()


def test_env_provider_returns_value_and_provider_name(monkeypatch):
    monkeypatch.setenv("TESTKEY", "s3cret")
    assert resolve_secret("TESTKEY", provider="env") == ("s3cret", "env")


def test_auto_falls_back_to_env_when_op_reference_unset(monkeypatch):
    monkeypatch.setenv("TESTKEY", "s3cret")
    secret, provider = resolve_secret("TESTKEY")  # auto
    assert (secret, provider) == ("s3cret", "env")


def test_1password_leg_reads_op_reference(monkeypatch):
    monkeypatch.setenv("PIPYER_TESTKEY_OP_REFERENCE", "op://vault/item/field")
    monkeypatch.setattr("secretpath.core.shutil.which", lambda _: "/usr/local/bin/op")

    class Proc:
        returncode = 0
        stdout = "from-op\n"
        stderr = ""

    monkeypatch.setattr("secretpath.core.subprocess.run", lambda *a, **k: Proc())
    assert resolve_secret("TESTKEY") == ("from-op", "1password")


def test_auto_prefers_1password_over_env(monkeypatch):
    monkeypatch.setenv("TESTKEY", "from-env")
    monkeypatch.setenv("PIPYER_TESTKEY_OP_REFERENCE", "op://vault/item/field")
    monkeypatch.setattr("secretpath.core.shutil.which", lambda _: "/usr/local/bin/op")

    class Proc:
        returncode = 0
        stdout = "from-op"
        stderr = ""

    monkeypatch.setattr("secretpath.core.subprocess.run", lambda *a, **k: Proc())
    assert resolve_secret("TESTKEY") == ("from-op", "1password")


def test_op_failure_falls_through_to_env_under_auto(monkeypatch):
    monkeypatch.setenv("TESTKEY", "from-env")
    monkeypatch.setenv("PIPYER_TESTKEY_OP_REFERENCE", "op://vault/item/field")
    monkeypatch.setattr("secretpath.core.shutil.which", lambda _: "/usr/local/bin/op")

    class Proc:
        returncode = 1
        stdout = ""
        stderr = "op: not signed in"

    monkeypatch.setattr("secretpath.core.subprocess.run", lambda *a, **k: Proc())
    assert resolve_secret("TESTKEY") == ("from-env", "env")


def test_exhaustion_names_every_attempt():
    with pytest.raises(SecretResolutionError) as excinfo:
        resolve_secret("TESTKEY")
    message = str(excinfo.value)
    assert "TESTKEY" in message
    assert "1password" in message and "env" in message


def test_unknown_provider_rejected():
    with pytest.raises(SecretResolutionError, match="unknown secret provider"):
        resolve_secret("TESTKEY", provider="keychain")


def test_explicit_env_provider_never_touches_op(monkeypatch):
    monkeypatch.setenv("PIPYER_TESTKEY_OP_REFERENCE", "op://vault/item/field")

    def boom(*a, **k):
        raise AssertionError("op must not run under provider='env'")

    monkeypatch.setattr("secretpath.core.subprocess.run", boom)
    with pytest.raises(SecretResolutionError):
        resolve_secret("TESTKEY", provider="env")
