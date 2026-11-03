"""Claude-powered natural language to SQL agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

from jarvis.db import Database

BLOCKED_KEYWORDS = {"DROP DATABASE", "DROP SCHEMA", "TRUNCATE"}

SYSTEM_PROMPT = """\
You are Jarvis, an intelligent database assistant. Users talk to you in plain English \
and you translate their requests into SQL, execute them, and explain the results.

## Database Schema
{schema}

## Rules
1. Generate valid PostgreSQL SQL based on the schema above.
2. For SELECT queries, call execute_sql right away.
3. For INSERT/UPDATE/DELETE, explain what the query will do, then call execute_sql.
4. NEVER generate DROP DATABASE, DROP SCHEMA, or TRUNCATE statements.
5. When results come back, give a clear, concise human-readable answer.
6. If the request is ambiguous, state your assumptions.
7. If extra context is provided (like user_id), use it to scope queries appropriately.
8. Limit SELECT results to 100 rows unless the user asks for more.
"""

TOOLS = [
    {
        "name": "execute_sql",
        "description": "Execute a SQL query against the PostgreSQL database and return results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The SQL query to execute.",
                },
                "is_destructive": {
                    "type": "boolean",
                    "description": "True if this query modifies data (INSERT, UPDATE, DELETE, ALTER, etc.).",
                },
            },
            "required": ["sql", "is_destructive"],
        },
    }
]


@dataclass
class QueryResult:
    answer: str
    sql: str | None = None
    raw_results: dict | None = None
    is_destructive: bool = False
    blocked: bool = False
    error: str | None = None


@dataclass
class Agent:
    db: Database
    model: str = "claude-sonnet-4-20250514"
    read_only: bool = False
    _client: anthropic.Anthropic = field(default_factory=anthropic.Anthropic)
    _schema: str = ""

    def initialize(self) -> None:
        self.db.connect()
        self._schema = self.db.introspect_schema()

    def query(
        self,
        message: str,
        user_context: dict | None = None,
        conversation: list[dict] | None = None,
        auto_execute_destructive: bool = False,
    ) -> QueryResult:
        system = SYSTEM_PROMPT.format(schema=self._schema)
        if user_context:
            system += f"\n\n## User Context\n{json.dumps(user_context)}"
        if self.read_only:
            system += "\n\n## IMPORTANT: Read-only mode is ON. Only generate SELECT queries."

        messages = list(conversation) if conversation else []
        messages.append({"role": "user", "content": message})

        response = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        return self._process_response(
            response, messages, system, auto_execute_destructive
        )

    def _process_response(
        self,
        response: anthropic.types.Message,
        messages: list[dict],
        system: str,
        auto_execute_destructive: bool,
    ) -> QueryResult:
        if response.stop_reason == "end_turn":
            text = next(
                (b.text for b in response.content if b.type == "text"), ""
            )
            return QueryResult(answer=text)

        if response.stop_reason != "tool_use":
            text = next(
                (b.text for b in response.content if b.type == "text"), ""
            )
            return QueryResult(answer=text or "I couldn't process that request.")

        tool_block = next(b for b in response.content if b.type == "tool_use")
        sql = tool_block.input["sql"]
        is_destructive = tool_block.input.get("is_destructive", False)

        # Safety checks
        sql_upper = sql.upper()
        for kw in BLOCKED_KEYWORDS:
            if kw in sql_upper:
                return QueryResult(
                    answer=f"Blocked: `{kw}` operations are not allowed.",
                    sql=sql,
                    is_destructive=True,
                    blocked=True,
                )

        if self.read_only and is_destructive:
            return QueryResult(
                answer="Blocked: database is in read-only mode.",
                sql=sql,
                is_destructive=True,
                blocked=True,
            )

        if is_destructive and not auto_execute_destructive:
            return QueryResult(
                answer="This is a destructive query. Please confirm execution.",
                sql=sql,
                is_destructive=True,
            )

        # Execute the query
        result = self.db.execute(sql)

        if not result["success"]:
            tool_result_content = json.dumps({"error": result["error"]})
        else:
            tool_result_content = json.dumps(result, default=str)

        # Feed results back to Claude for a human-readable answer
        messages.append({"role": "assistant", "content": response.content})
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": tool_result_content,
                    }
                ],
            }
        )

        follow_up = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        # Handle potential chained tool calls (agent might need multiple queries)
        if follow_up.stop_reason == "tool_use":
            return self._process_response(
                follow_up, messages, system, auto_execute_destructive
            )

        answer = next(
            (b.text for b in follow_up.content if b.type == "text"), ""
        )
        return QueryResult(
            answer=answer,
            sql=sql,
            raw_results=result,
            is_destructive=is_destructive,
        )

    def execute_confirmed(self, sql: str) -> QueryResult:
        """Execute a previously confirmed destructive query."""
        result = self.db.execute(sql)
        if not result["success"]:
            return QueryResult(
                answer=f"Error: {result['error']}",
                sql=sql,
                error=result["error"],
                is_destructive=True,
            )
        affected = result.get("rows_affected", 0)
        return QueryResult(
            answer=f"Done. {affected} row(s) affected.",
            sql=sql,
            raw_results=result,
            is_destructive=True,
        )
