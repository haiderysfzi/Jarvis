"""Interactive CLI for Jarvis — talk to your database from the terminal."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from jarvis.agent import Agent
from jarvis.db import Database
from jarvis.llm import create_provider


def main():
    load_dotenv()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("Error: DATABASE_URL not set. Copy .env.example to .env and configure it.")
        sys.exit(1)

    provider_name = os.environ.get("JARVIS_PROVIDER", "anthropic")
    model = os.environ.get("JARVIS_MODEL")
    read_only = os.environ.get("JARVIS_READ_ONLY", "false").lower() == "true"

    llm = create_provider(
        provider=provider_name,
        model=model,
        api_key=os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"),
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
    )

    db = Database(dsn)
    agent = Agent(db=db, llm=llm, read_only=read_only)

    print("Connecting to database...")
    agent.initialize()
    print(f"Ready. Provider: {provider_name} | Model: {model or 'default'} | Read-only: {read_only}")
    print("Type your query in plain English. Commands: /schema, /quit\n")

    pending_sql: str | None = None

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
            print("Bye.")
            break

        if user_input.lower() == "/schema":
            print(agent.schema)
            continue

        if pending_sql and user_input.lower() in ("yes", "y", "confirm"):
            result = agent.execute_confirmed(pending_sql)
            print(f"\nJarvis: {result.answer}")
            if result.sql:
                print(f"  SQL: {result.sql}")
            pending_sql = None
            print()
            continue

        if pending_sql and user_input.lower() in ("no", "n", "cancel"):
            print("\nJarvis: Cancelled.\n")
            pending_sql = None
            continue

        pending_sql = None
        result = agent.query(message=user_input, auto_execute_destructive=False)

        print(f"\nJarvis: {result.answer}")
        if result.sql:
            print(f"  SQL: {result.sql}")

        if result.is_destructive and not result.blocked and result.raw_results is None:
            pending_sql = result.sql
            print("  Confirm? (yes/no)")

        print()

    db.close()


if __name__ == "__main__":
    main()
