"""Provider registry — resolve a provider name to an LLMProvider instance."""

from __future__ import annotations

from jarvis.llm.base import LLMProvider


def create_provider(
    provider: str = "anthropic",
    model: str | None = None,
    api_key: str | None = None,
    **kwargs,
) -> LLMProvider:
    if provider == "anthropic":
        from jarvis.llm.anthropic import AnthropicProvider
        return AnthropicProvider(
            model=model or "claude-sonnet-4-20250514",
            api_key=api_key,
        )

    if provider == "openai":
        from jarvis.llm.openai import OpenAIProvider
        return OpenAIProvider(
            model=model or "gpt-4o",
            api_key=api_key,
            base_url=kwargs.get("base_url"),
        )

    if provider == "gemini":
        from jarvis.llm.gemini import GeminiProvider
        return GeminiProvider(
            model=model or "gemini-2.5-flash",
            api_key=api_key,
        )

    if provider == "ollama":
        from jarvis.llm.ollama import OllamaProvider
        return OllamaProvider(
            model=model or "llama3.1",
            base_url=kwargs.get("ollama_base_url", "http://localhost:11434"),
        )

    raise ValueError(
        f"Unknown provider '{provider}'. Available: anthropic, openai, gemini, ollama"
    )
