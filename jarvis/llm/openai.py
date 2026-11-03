"""OpenAI provider for Jarvis."""

from __future__ import annotations

import json

from openai import OpenAI

from jarvis.llm.base import LLMProvider, LLMResponse

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "Execute a SQL query against the database.",
            "parameters": {
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
        },
    }
]


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4o", api_key: str | None = None, base_url: str | None = None):
        self._model = model
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)

    def generate_sql(
        self,
        schema: str,
        user_message: str,
        user_context: dict | None = None,
        read_only: bool = False,
    ) -> LLMResponse:
        system = self._build_system(schema, user_context, read_only)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            tools=TOOLS,
        )

        msg = response.choices[0].message
        if msg.tool_calls:
            call = msg.tool_calls[0]
            args = json.loads(call.function.arguments)
            return LLMResponse(
                sql=args["sql"],
                is_destructive=args.get("is_destructive", False),
                needs_execution=True,
            )

        return LLMResponse(text=msg.content or "")

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
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""

    def _build_system(
        self, schema: str, user_context: dict | None, read_only: bool
    ) -> str:
        parts = [
            "You are a database assistant. Generate PostgreSQL SQL to answer the user's question.\n",
            f"## Schema\n{schema}\n",
            "## Rules\n"
            "- Call the execute_sql function with the SQL query.\n"
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
