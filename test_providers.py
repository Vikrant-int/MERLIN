"""Provider abstraction tests: Mock/development mode vs the Gemini wrapper.

These run with **no network and no API key**. They prove that:
* the Mock provider returns deterministic, clearly-marked development replies
  that are never mistaken for Gemini output;
* provider resolution honours an explicit mode, the MERLIN_PROVIDER
  environment variable and falls back to a safe default;
* the Gemini provider still delegates to the backend wrapper (and therefore
  preserves the existing honest missing-key behaviour);
* a fresh machine with no key can still resolve a working provider.

Run:  myprojectenv\\Scripts\\python.exe test_providers.py
"""
from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, ".")

from services.ai_provider import (  # noqa: E402
    PROVIDER_AUTO,
    PROVIDER_GEMINI,
    PROVIDER_MOCK,
    GeminiProvider,
    MockProvider,
    effective_provider,
    is_dev_mode,
    provider_label,
    resolve_provider,
)
from services.assistant_service import is_backend_failure  # noqa: E402

_checks = 0
_failures: list[str] = []


def ensure(condition: bool, message: str) -> bool:
    global _checks
    _checks += 1
    if condition:
        print(f"  [PASS] {message}")
        return True
    _failures.append(message)
    print(f"  [FAIL] {message}")
    return False


class _FakeGemini:
    """A real backend GeminiChat stand-in that records how it was called."""

    def __init__(self, reply: str = "stub answer"):
        self.reply = reply
        self._config_error = None
        self.calls: list[tuple] = []
        self.resets = 0

    def send(self, message, retries=2):  # noqa: ANN001
        self.calls.append((message, retries))
        return self.reply

    def reset(self):
        self.resets += 1
        return None


class _UnconfiguredGemini:
    """Main.py's real unconfigured shape: answers with the friendly error."""

    backend = "unconfigured"
    _config_error = (
        "GEMINI_API_KEY is not set. Create one at "
        "https://aistudio.google.com/apikey and run: "
        "setx GEMINI_API_KEY \"<your key>\" (then open a new terminal)"
    )

    def send(self, message, retries=2):  # noqa: ANN001, ARG002
        return self._config_error

    def reset(self):
        return None


def _backend(gemini=None):
    return types.SimpleNamespace(
        API_KEY="stub" if gemini is None else None,
        MODEL_NAME="gemini-2.5-flash",
        gemini=gemini if gemini is not None else _FakeGemini(),
    )


# ==========================================================================
# 1. Mock provider
# ==========================================================================
print("\n== mock provider ==")

_mock = MockProvider()
_r1 = _mock.send("tell me a joke")
_r2 = _mock.send("what is the capital of France?")
ensure(_r1 == _r2, "mock replies are deterministic (same text for any input)")
ensure("development mode" in _r1.lower(),
       "mock reply is not clearly marked as development mode")
ensure("Mock" in _r1, "mock reply does not name the Mock provider")
ensure("Gemini" in _r1, "mock reply does not name what it replaces")
ensure("GEMINI_API_KEY" in _r1, "mock reply gives no pointer to the key")
ensure(_mock.reset() is None, "mock reset is a harmless no-op")

# The chat surface must render mock replies as normal assistant bubbles:
# they are not one of the backend-failure phrases.
ensure(not is_backend_failure(_r1),
       "mock reply is not misread as a backend failure")

# ==========================================================================
# 2. Resolution
# ==========================================================================
print("\n== provider resolution ==")

# Guard the environment so a developer's machine cannot skew the results.
_old_env = os.environ.get("MERLIN_PROVIDER")
_old_key = os.environ.get("GEMINI_API_KEY")
if "MERLIN_PROVIDER" in os.environ:
    del os.environ["MERLIN_PROVIDER"]
if "GEMINI_API_KEY" in os.environ:
    del os.environ["GEMINI_API_KEY"]
try:
    ensure(effective_provider(PROVIDER_MOCK) == "mock",
           "explicit mock mode is honoured")
    ensure(effective_provider(PROVIDER_GEMINI) == "gemini",
           "explicit gemini mode is honoured")
    ensure(effective_provider(PROVIDER_AUTO) == "auto",
           "explicit auto mode is honoured")
    ensure(effective_provider("") == "auto", "empty mode falls back to auto")
    ensure(effective_provider("bogus") == "auto",
           "unknown mode falls back to auto")
    ensure(effective_provider(None) == "auto",
           "no mode falls back to auto with no environment override")

    ensure(isinstance(resolve_provider(PROVIDER_MOCK), MockProvider),
           "mock mode resolves to the Mock provider")
    ensure(isinstance(resolve_provider(PROVIDER_GEMINI), GeminiProvider),
           "gemini mode resolves to the Gemini provider")
    ensure(isinstance(resolve_provider(PROVIDER_AUTO), GeminiProvider),
           "auto mode resolves to the Gemini provider")
    # The critical absence test: no key, no environment, still resolvable.
    ensure(resolve_provider() is not None,
           "a machine with no key still gets a working provider")
finally:
    if _old_env is None:
        os.environ.pop("MERLIN_PROVIDER", None)
    else:
        os.environ["MERLIN_PROVIDER"] = _old_env
    if _old_key is None:
        os.environ.pop("GEMINI_API_KEY", None)
    else:
        os.environ["GEMINI_API_KEY"] = _old_key

# Environment override (fresh-install seeding path).
os.environ["MERLIN_PROVIDER"] = "mock"
try:
    ensure(effective_provider(None) == "mock",
           "MERLIN_PROVIDER=mock selects development mode")
    ensure(is_dev_mode(None), "is_dev_mode reports true for mock")
    ensure(provider_label(None) == "Mock (development)",
           "provider label names the Mock provider")
finally:
    os.environ.pop("MERLIN_PROVIDER", None)
ensure(effective_provider(None) == "auto",
       "removing MERLIN_PROVIDER restores the default")

# ==========================================================================
# 3. Gemini provider delegates to the backend wrapper
# ==========================================================================
print("\n== gemini provider delegation ==")

_backend_gemini = _FakeGemini("a real answer")
_backend_obj = _backend(_backend_gemini)
_gemini_provider = GeminiProvider(get_backend=lambda: _backend_obj)

ensure(_gemini_provider.name == "gemini", "gemini provider knows its name")
reply = _gemini_provider.send("hello", retries=3)
ensure(reply == "a real answer", "provider hands back the backend reply")
ensure(_backend_gemini.calls == [("hello", 3)],
       "message and retry count reached the backend")
_gemini_provider.reset()
ensure(_backend_gemini.resets == 1, "reset reached the backend")

# The provider must preserve the backend's honest missing-key message so the
# unconfigured experience is unchanged (the UI baseline depends on it).
_unconf = _UnconfiguredGemini()
_unconf_provider = GeminiProvider(get_backend=lambda: _backend(_unconf))
missing = _unconf_provider.send("what is the capital of France?")
ensure("GEMINI_API_KEY is not set" in missing,
       "missing-key behaviour goes through the provider intact")
ensure("Traceback" not in missing, "missing-key message is user friendly")
ensure(is_backend_failure(missing),
       "the missing-key message is still read as a backend failure")
_with_key = GeminiProvider(get_backend=lambda: _backend())
ensure(not is_backend_failure(_with_key.send("ok")),
       "a real backend reply is not misread as a failure")


# ==========================================================================
print(f"\n{_checks - len(_failures)}/{_checks} provider checks passed")
if _failures:
    print("Failed:")
    for name in _failures:
        print(f"  - {name}")
    sys.exit(1)
print("ALL PROVIDER CHECKS PASSED")
sys.exit(0)