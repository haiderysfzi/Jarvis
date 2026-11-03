"""Abstract LLM provider interface — Jarvis talks to any backend through this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Unified response from any LLM backend."""
    text: str | None = None
    sql: str | None = None
    is_destructive: bool = False
    needs_execution: bool = False


class LLMProvider(ABC):
    """Any LLM that Jarvis can use as its brain."""

    @abstractmethod
    def generate_sql(
        self,
        schema: str,
        user_message: str,
        user_context: dict | None = None,
        read_only: bool = False,
    ) -> LLMResponse:
        """Given a schema and a natural language query, produce SQL."""

    @abstractmethod
    def explain_results(
        self,
        user_message: str,
        sql: str,
        results: dict,
        schema: str,
    ) -> str:
        """Given query results, produce a human-readable explanation."""
