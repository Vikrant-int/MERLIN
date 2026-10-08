"""AI provider abstraction: a Mock/development provider and the Gemini one.

The UI must start, answer and explain itself on a machine with no API key,
so the chat surface talks to a *provider* instead of reaching for Gemini
directly.

* ``Auto`` (the default) delegates to the real backend wrapper, which is the
  honest behaviour the rest of the project already had: configured means
  real Gemini answers, unconfigured means a clear explanation of what is
  missing.
* ``Mock`` is the development provider. It needs no key, no backend import
  and no network, and every reply is a deterministic placeholder that is
  clearly stamped as *not* coming from Gemini.
* ``Gemini`` always delegates to the backend wrapper.

Nothing in this module ever reads a key value, and nothing prints to
stdout, so a credential cannot leak through it.
"""
from __future__ import annotations

import os
from typing import Protocol

from .core import get_main

# Machine-level default; documented in .env.example.
ENV_NAME = "MERLIN_PROVIDER"

PROVIDER_AUTO = "auto"
PROVIDER_MOCK = "mock"
PROVIDER_GEMINI = "gemini"
PROVIDERS = (PROVIDER_AUTO, PROVIDER_MOCK, PROVIDER_GEMINI)

# Every Mock reply is this exact string. Deterministic on purpose: a test
# or a user must be able to tell a placeholder from a live answer across
# restarts. The text explicitly says Gemini is off so nothing is ever
# mistaken for a real model reply.
_MOCK_REPLY = (
    "MERLIN development mode: the Gemini API is not connected, so this is a "
    "local placeholder answer from the Mock provider, not a real Gemini "
    "reply. Set GEMINI_API_KEY and use Auto or Gemini mode in Settings to "
    "get live answers."
)


class ChatProvider(Protocol):
    """What the chat surface needs from any AI backend."""

    name: str

    def send(self, message: str, retries: int = 2) -> str: ...
    def reset(self) -> None: ...


class MockProvider:
    """Deterministic development provider. No key, no backend, no network."""

    name = PROVIDER_MOCK

    def send(self, message: str, retries: int = 2) -> str:  # noqa: ANN001, ARG002
        return _MOCK_REPLY

    def reset(self) -> None:
        return None


class GeminiProvider:
    """Delegates to the backend's own Gemini wrapper.

    The backend object is reached through ``get_backend`` -- normally
    :func:`services.core.get_main` -- so the provider stays on the thread
    that owns the speech engine, exactly like the rest of the UI services.
    Unconfigured backends already answer with a friendly explanation, which
    is what surfaces when GEMINI_API_KEY is missing.
    """

    name = PROVIDER_GEMINI

    def __init__(self, get_backend=None):
        self._get_backend = get_backend or get_main

    def send(self, message: str, retries: int = 2) -> str:
        return self._get_backend().gemini.send(message, retries=retries)

    def reset(self) -> None:
        return self._get_backend().gemini.reset()


def effective_provider(mode: str | None = None) -> str:
    """The validated provider name, falling back to the environment.

    Explicit mode (from the Settings store or a caller) wins; otherwise
    ``MERLIN_PROVIDER``; otherwise ``auto``. Anything unrecognised is
    treated as ``auto`` so a stale value can never break the app.
    """
    if mode in PROVIDERS:
        return mode
    env = (os.getenv(ENV_NAME) or "").strip().lower()
    return env if env in PROVIDERS else PROVIDER_AUTO


def is_dev_mode(mode: str | None = None) -> bool:
    return effective_provider(mode) == PROVIDER_MOCK


def resolve_provider(mode: str | None = None,
                     get_backend=None) -> ChatProvider:
    """Build the provider for ``mode`` (validated, env-aware)."""
    if effective_provider(mode) == PROVIDER_MOCK:
        return MockProvider()
    return GeminiProvider(get_backend=get_backend)


def provider_label(mode: str | None = None) -> str:
    return {
        PROVIDER_AUTO: "Auto",
        PROVIDER_MOCK: "Mock (development)",
        PROVIDER_GEMINI: "Gemini",
    }[effective_provider(mode)]