# Jarvis

Natural language database agent. Talk to your PostgreSQL database in plain English — Jarvis translates your words into SQL, runs it, and explains the results back to you.

Built on Claude as the reasoning engine.

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your DATABASE_URL and ANTHROPIC_API_KEY
```

### CLI

```bash
python main.py
```

```
You: How many users signed up this week?
Jarvis: 34 users signed up in the last 7 days.
  SQL: SELECT COUNT(*) FROM users WHERE created_at >= NOW() - INTERVAL '7 days'

You: Delete all posts by user 5
Jarvis: This will delete 12 posts by user 5 permanently.
  SQL: DELETE FROM posts WHERE user_id = 5
  Confirm? (yes/no)
```

Commands: `/schema` to see the database structure, `/quit` to exit.

### REST API

```bash
python main.py serve              # localhost:8000
python main.py serve 0.0.0.0 9000 # custom host/port
```

**Query:**
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"message": "how many games have I played?", "user_context": {"user_id": 42}}'
```

```json
{
  "answer": "You've played 137 games total.",
  "sql": "SELECT COUNT(*) FROM games WHERE user_id = 42",
  "is_destructive": false,
  "requires_confirmation": false
}
```

**Destructive queries** return `requires_confirmation: true` unless you pass `"auto_execute": true`. Confirm with:

```bash
curl -X POST http://localhost:8000/confirm \
  -H "Content-Type: application/json" \
  -d '{"sql": "DELETE FROM posts WHERE user_id = 5"}'
```

**Other endpoints:**
- `GET /schema` — the database schema Jarvis sees
- `GET /health` — health check
- `GET /docs` — interactive API docs (Swagger)

### In-process (integrate into existing code)

```python
from jarvis.db import Database
from jarvis.agent import Agent

db = Database("postgresql://user:pass@localhost:5432/mydb")
agent = Agent(db=db)
agent.initialize()

result = agent.query("how many games have I played?", user_context={"user_id": 42})
print(result.answer)  # "You've played 137 games total."
print(result.sql)     # "SELECT COUNT(*) FROM games WHERE user_id = 42"
```

## Configuration

Set these in `.env`:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `JARVIS_READ_ONLY` | No | `true` to block all write operations (default: `false`) |
| `JARVIS_MODEL` | No | Claude model to use (default: `claude-sonnet-4-20250514`) |

## Safety

- **Destructive queries** (INSERT, UPDATE, DELETE) require explicit confirmation
- **DROP DATABASE, DROP SCHEMA, TRUNCATE** are blocked entirely
- **Read-only mode** disables all write operations
- **Query timeout** at 30 seconds prevents runaway queries
- **Results capped** at 500 rows per query

Tip: connect with a read-only database user for maximum safety.

## How it works

1. On startup, Jarvis introspects your Postgres schema — tables, columns, types, primary keys, foreign keys, approximate row counts
2. The full schema is included in Claude's system prompt so it knows your data model
3. Your plain-English query goes to Claude, which generates SQL via tool use
4. The SQL executes against Postgres and results feed back to Claude
5. Claude returns a human-readable answer

Multi-step queries are supported — Claude can chain multiple SQL calls to answer complex questions.
