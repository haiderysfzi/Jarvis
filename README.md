# Jarvis

Natural language database agent. Talk to your PostgreSQL database in plain English — Jarvis translates your words into SQL, runs it, and explains the results.

Jarvis is the agent. The LLM is a pluggable tool it uses — swap between Claude, GPT, or local models via Ollama without changing a line of code.

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set DATABASE_URL and your LLM provider
```

### Pick your LLM

| Provider | `JARVIS_PROVIDER` | Key needed | Default model |
|---|---|---|---|
| Claude | `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-4o` |
| Ollama | `ollama` | None (local) | `llama3.1` |

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
- `GET /docs` — interactive Swagger UI

### In-process (integrate into existing code)

```python
from jarvis.db import Database
from jarvis.agent import Agent
from jarvis.llm import create_provider

llm = create_provider("ollama", model="llama3.1")  # or "anthropic", "openai"
db = Database("postgresql://user:pass@localhost:5432/mydb")
agent = Agent(db=db, llm=llm)
agent.initialize()

result = agent.query("how many games have I played?", user_context={"user_id": 42})
print(result.answer)  # "You've played 137 games total."
```

## Architecture

```
┌──────────────────────────────────────────────┐
│                   Jarvis Agent               │
│                                              │
│  ┌─────────┐   ┌──────────┐   ┌──────────┐  │
│  │ Safety   │   │ Schema   │   │ Query    │  │
│  │ & Rules  │   │ Context  │   │ Executor │  │
│  └─────────┘   └──────────┘   └──────────┘  │
│        │              │              │       │
│        └──────────────┼──────────────┘       │
│                       │                      │
│              ┌────────┴────────┐             │
│              │   LLM Provider  │             │
│              │   (pluggable)   │             │
│              └────────┬────────┘             │
│          ┌────────────┼────────────┐         │
│          ▼            ▼            ▼         │
│      Anthropic     OpenAI      Ollama        │
│      (Claude)      (GPT)      (Local)        │
└──────────────────────────────────────────────┘
         │
    ┌────┴────┐
    │Postgres │
    └─────────┘
```

Jarvis owns:
- **Schema introspection** — reads your tables, columns, PKs, FKs, row counts
- **Safety enforcement** — blocks dangerous ops, confirms destructive queries, read-only mode
- **Query execution** — runs SQL with timeouts, caps results
- **The conversation flow** — NL in, SQL generated, results explained

The LLM just does language: turning English into SQL, and results into English.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `JARVIS_PROVIDER` | No | `anthropic`, `openai`, or `ollama` (default: `anthropic`) |
| `ANTHROPIC_API_KEY` | If anthropic | Claude API key |
| `OPENAI_API_KEY` | If openai | OpenAI API key |
| `OLLAMA_BASE_URL` | If ollama | Ollama server URL (default: `http://localhost:11434`) |
| `JARVIS_MODEL` | No | Override the default model for your provider |
| `JARVIS_READ_ONLY` | No | `true` to block all write operations |

## Safety

- **Destructive queries** (INSERT, UPDATE, DELETE) require explicit confirmation
- **DROP DATABASE, DROP SCHEMA, TRUNCATE** are blocked entirely
- **Read-only mode** disables all write operations
- **Query timeout** at 30 seconds prevents runaway queries
- **Results capped** at 500 rows per query

Tip: connect with a read-only database user for maximum safety.
