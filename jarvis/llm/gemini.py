"""Google Gemini provider for Jarvis."""

from __future__ import annotations

import json

from google import genai
from google.genai import types

from jarvis.llm.base import LLMProvider, LLMResponse

EXECUTE_SQL_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="execute_sql",
            description="Execute a SQL query against the database.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "sql": types.Schema(type="STRING", description="The SQL query."),
                    "is_destructive": types.Schema(
                        type="BOOLEAN",
                        description="True if this modifies data.",
                    ),
                },
                required=["sql", "is_destructive"],
            ),
        )
    ]
)


class GeminiProvider(LLMProvider):
    def __init__(self, model: str = "gemini-2.5-flash", api_key: str | None = None):
        self._model = model
        self._client = genai.Client(api_key=api_key) if api_key else genai.Client()

    def generate_sql(
        self,
        schema: str,
        user_message: str,
        user_context: dict | None = None,
        read_only: bool = False,
    ) -> LLMResponse:
        system = self._build_system(schema, user_context, read_only)
        response = self._client.models.generate_content(
            model=self._model,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system,
                tools=[EXECUTE_SQL_TOOL],
            ),
        )

        part = response.candidates[0].content.parts[0]
        if part.function_call:
            args = dict(part.function_call.args)
            return LLMResponse(
                sql=args["sql"],
                is_destructive=bool(args.get("is_destructive", False)),
                needs_execution=True,
            )

        return LLMResponse(text=part.text or "")

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
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
        )
        return response.candidates[0].content.parts[0].text or ""

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
