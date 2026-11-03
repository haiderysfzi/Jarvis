"""Jarvis — the agent. The LLM is a tool it uses, not the other way around."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from jarvis.db import Database
from jarvis.llm import LLMProvider, create_provider

BLOCKED_PATTERNS = re.compile(
    r"\b(DROP\s+DATABASE|DROP\s+SCHEMA|TRUNCATE)\b", re.IGNORECASE
)


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
    """Jarvis core. Owns the database connection, enforces safety rules,
    delegates language understanding to whichever LLM provider is configured."""

    db: Database
    llm: LLMProvider = field(default=None)
    read_only: bool = False
    _schema: str = ""

    def __post_init__(self):
        if self.llm is None:
            self.llm = create_provider()

    def initialize(self) -> None:
        self.db.connect()
        self._schema = self.db.introspect_schema()

    @property
    def schema(self) -> str:
        return self._schema

    def query(
        self,
        message: str,
        user_context: dict | None = None,
        auto_execute_destructive: bool = False,
    ) -> QueryResult:
        # Step 1: Ask the LLM to produce SQL
        llm_response = self.llm.generate_sql(
            schema=self._schema,
            user_message=message,
            user_context=user_context,
            read_only=self.read_only,
        )

        # LLM answered directly without SQL (e.g. clarification question)
        if not llm_response.needs_execution:
            return QueryResult(answer=llm_response.text or "I couldn't understand that.")

        sql = llm_response.sql

        # Step 2: Jarvis validates the SQL before it touches the database
        if blocked := self._check_blocked(sql):
            return blocked

        if self.read_only and llm_response.is_destructive:
            return QueryResult(
                answer="Blocked: database is in read-only mode.",
                sql=sql,
                is_destructive=True,
                blocked=True,
            )

        if llm_response.is_destructive and not auto_execute_destructive:
            return QueryResult(
                answer="This is a destructive query. Please confirm execution.",
                sql=sql,
                is_destructive=True,
            )

        # Step 3: Jarvis executes
        result = self.db.execute(sql)

        if not result["success"]:
            return QueryResult(
                answer=f"Query failed: {result['error']}",
                sql=sql,
                error=result["error"],
            )

        # Step 4: Ask the LLM to explain the results in plain language
        answer = self.llm.explain_results(
            user_message=message,
            sql=sql,
            results=result,
            schema=self._schema,
        )

        return QueryResult(
            answer=answer,
            sql=sql,
            raw_results=result,
            is_destructive=llm_response.is_destructive,
        )

    def execute_confirmed(self, sql: str) -> QueryResult:
        """Execute a previously confirmed destructive query."""
        if blocked := self._check_blocked(sql):
            return blocked

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

    def _check_blocked(self, sql: str) -> QueryResult | None:
        if BLOCKED_PATTERNS.search(sql):
            return QueryResult(
                answer="Blocked: this operation is not allowed.",
                sql=sql,
                is_destructive=True,
                blocked=True,
            )
        return None
