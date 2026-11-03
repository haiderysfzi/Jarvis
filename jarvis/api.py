"""FastAPI REST API for Jarvis — integrate into any system via HTTP."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    anthropic_api_key: str
    jarvis_read_only: bool = False
    jarvis_model: str = "claude-sonnet-4-20250514"

    model_config = {"env_file": ".env"}


class QueryRequest(BaseModel):
    message: str
    user_context: dict | None = None
    auto_execute: bool = False


class ConfirmRequest(BaseModel):
    sql: str


class QueryResponse(BaseModel):
    answer: str
    sql: str | None = None
    is_destructive: bool = False
    requires_confirmation: bool = False
    blocked: bool = False
    results: dict | None = None


settings = Settings()

# Late import to avoid circular issues at module level
from jarvis.agent import Agent  # noqa: E402
from jarvis.db import Database  # noqa: E402

_agent: Agent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    db = Database(settings.database_url)
    _agent = Agent(
        db=db,
        model=settings.jarvis_model,
        read_only=settings.jarvis_read_only,
    )
    _agent.initialize()
    yield
    db.close()


app = FastAPI(
    title="Jarvis",
    description="Natural language database agent — talk to your Postgres in plain English.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    result = _agent.query(
        message=req.message,
        user_context=req.user_context,
        auto_execute_destructive=req.auto_execute,
    )
    return QueryResponse(
        answer=result.answer,
        sql=result.sql,
        is_destructive=result.is_destructive,
        requires_confirmation=result.is_destructive and not result.blocked and result.raw_results is None,
        blocked=result.blocked,
        results=result.raw_results,
    )


@app.post("/confirm", response_model=QueryResponse)
def confirm(req: ConfirmRequest):
    result = _agent.execute_confirmed(req.sql)
    return QueryResponse(
        answer=result.answer,
        sql=result.sql,
        is_destructive=True,
        results=result.raw_results,
    )


@app.get("/schema")
def schema():
    return {"schema": _agent._schema}


@app.get("/health")
def health():
    return {"status": "ok"}
