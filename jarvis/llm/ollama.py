"""Ollama provider for Jarvis — use local models, no API keys needed."""

from __future__ import annotations

import json
import re

import requests

from jarvis.llm.base import LLMProvider, LLMResponse

SQL_EXTRACTION = re.compile(r"```sql\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
DESTRUCTIVE_PREFIXES = ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE")


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        model: str = "llama3.1",
        base_url: str = "http://localhost:11434",
    ):
        self._model = model
        self._base_url = base_url.rstrip("/")

    def generate_sql(
        self,
        schema: str,
        user_message: str,
        user_context: dict | None = None,
        read_only: bool = False,
    ) -> LLMResponse:
        system = self._build_system(schema, user_context, read_only)
        prompt = (
            f"{system}\n\n"
            "IMPORTANT: PostgreSQL lowercases unquoted identifiers. Always double-quote column and table names that contain uppercase letters, e.g. \"publisherId\" not publisherId. Use identifiers exactly as shown in the schema.\n\n"
            f"User: {user_message}\n\n"
            "Respond with ONLY a SQL query inside a ```sql code block. Nothing else."
        )

        text = self._chat(prompt)
        match = SQL_EXTRACTION.search(text)
        if not match:
            return LLMResponse(text=text)

        sql = match.group(1).strip()
        is_destructive = sql.upper().lstrip().startswith(DESTRUCTIVE_PREFIXES)
        return LLMResponse(sql=sql, is_destructive=is_destructive, needs_execution=True)

    def explain_results(
        self,
        user_message: str,
        sql: str,
        results: dict,
        schema: str,
    ) -> str:
        prompt = (
            f"The user asked: \"{user_message}\"\n"
            f"This SQL ran: {sql}\n"
            f"Results: {json.dumps(results, default=str)}\n\n"
            "Give a clear, concise answer to the user's question based on these results. "
            "No SQL, no code blocks — just a plain English answer."
        )
        return self._chat(prompt)

    def _chat(self, prompt: str) -> str:
        resp = requests.post(
            f"{self._base_url}/api/generate",
            json={"model": self._model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")

    def _build_system(
        self, schema: str, user_context: dict | None, read_only: bool
    ) -> str:
        parts = [
            "You are a database assistant. Generate PostgreSQL SQL to answer the user's question.\n",
            f"## Schema\n{schema}\n",
        ]
        if user_context:
            parts.append(f"## User Context\n{json.dumps(user_context)}\n")
        if read_only:
            parts.append("IMPORTANT: Read-only mode. Only generate SELECT queries.\n")
        return "\n".join(parts)
