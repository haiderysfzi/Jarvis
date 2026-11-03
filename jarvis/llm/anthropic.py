"""Claude provider for Jarvis."""

from __future__ import annotations

import json

import anthropic

from jarvis.llm.base import LLMProvider, LLMResponse

TOOLS = [
    {
        "name": "execute_sql",
        "description": "Execute a SQL query against the database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "The SQL query."},
                "is_destructive": {
                    "type": "boolean",
                    "description": "True if this modifies data.",
                },
            },
            "required": ["sql", "is_destructive"],
        },
    }
]


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key: str | None = None):
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def generate_sql(
        self,
        schema: str,
        user_message: str,
        user_context: dict | None = None,
        read_only: bool = False,
    ) -> LLMResponse:
        system = self._build_system(schema, user_context, read_only)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=[{"role": "user", "content": user_message}],
        )

        if response.stop_reason == "tool_use":
            tool = next(b for b in response.content if b.type == "tool_use")
            return LLMResponse(
                sql=tool.input["sql"],
                is_destructive=tool.input.get("is_destructive", False),
                needs_execution=True,
            )

        text = next((b.text for b in response.content if b.type == "text"), "")
        return LLMResponse(text=text)

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
            "Give a clear, concise answer to the user's question based on these results."
        )
        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return next((b.text for b in response.content if b.type == "text"), "")

    def _build_system(
        self, schema: str, user_context: dict | None, read_only: bool
    ) -> str:
        parts = [
            "You are a database assistant. Generate PostgreSQL SQL to answer the user's question.\n",
            f"## Schema\n{schema}\n",
            "## Rules\n"
            "- Call the execute_sql tool with the SQL query.\n"
            "- IMPORTANT: PostgreSQL lowercases unquoted identifiers. Always double-quote column and table names that contain uppercase letters, e.g. \"publisherId\" not publisherId.\n"
            "- Use identifiers exactly as shown in the schema above (already quoted where needed).\n"
            "- Limit SELECTs to 100 rows unless asked otherwise.\n"
            "- Never generate DROP DATABASE, DROP SCHEMA, or TRUNCATE.\n"
            "- If ambiguous, state your assumptions.\n",
        ]
        if user_context:
            parts.append(f"## User Context\n{json.dumps(user_context)}\n")
        if read_only:
            parts.append("## IMPORTANT: Read-only mode. Only generate SELECT queries.\n")
        return "\n".join(parts)
