"""Interactive CLI for Jarvis — talk to your database from the terminal."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from jarvis.agent import Agent
from jarvis.db import Database


def main():
    load_dotenv()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("Error: DATABASE_URL not set. Copy .env.example to .env and configure it.")
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    model = os.environ.get("JARVIS_MODEL", "claude-sonnet-4-20250514")
    read_only = os.environ.get("JARVIS_READ_ONLY", "false").lower() == "true"

    db = Database(dsn)
    agent = Agent(db=db, model=model, read_only=read_only)

    print("Connecting to database...")
    agent.initialize()
    print(f"Ready. Connected to database. Model: {model}")
    print(f"Read-only: {read_only}")
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
            print(agent._schema)
            continue

        # Handle confirmation of destructive queries
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
