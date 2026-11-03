"""Database connection, schema introspection, and query execution."""

from __future__ import annotations

import re

import psycopg2
import psycopg2.extras

_PLAIN_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _quote(name: str) -> str:
    """Double-quote an identifier if it needs quoting in PostgreSQL."""
    if _PLAIN_IDENT.match(name):
        return name
    return f'"{name}"'


class Database:
    def __init__(self, dsn: str, statement_timeout_ms: int = 30_000):
        self._dsn = dsn
        self._timeout = statement_timeout_ms
        self._conn: psycopg2.extensions.connection | None = None

    def connect(self) -> None:
        self._conn = psycopg2.connect(
            self._dsn,
            options=f"-c statement_timeout={self._timeout}",
        )
        self._conn.set_session(autocommit=True)

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()

    @property
    def conn(self) -> psycopg2.extensions.connection:
        if self._conn is None or self._conn.closed:
            self.connect()
        return self._conn

    def introspect_schema(self, schemas: tuple[str, ...] = ("public",)) -> str:
        """Return a human-readable description of all tables, columns, PKs, and FKs."""
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Tables and columns
        cur.execute(
            """
            SELECT table_schema, table_name, column_name,
                   data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = ANY(%s)
            ORDER BY table_schema, table_name, ordinal_position
            """,
            (list(schemas),),
        )
        columns = cur.fetchall()

        # Primary keys
        cur.execute(
            """
            SELECT tc.table_schema, tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = ANY(%s)
            """,
            (list(schemas),),
        )
        pks: dict[str, list[str]] = {}
        for row in cur.fetchall():
            key = f"{row['table_schema']}.{row['table_name']}"
            pks.setdefault(key, []).append(_quote(row["column_name"]))

        # Foreign keys
        cur.execute(
            """
            SELECT
                tc.table_schema, tc.table_name, kcu.column_name,
                ccu.table_schema AS ref_schema,
                ccu.table_name AS ref_table,
                ccu.column_name AS ref_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = ANY(%s)
            """,
            (list(schemas),),
        )
        fks: dict[str, list[str]] = {}
        for row in cur.fetchall():
            key = f"{row['table_schema']}.{row['table_name']}"
            fk = f"{_quote(row['column_name'])} -> {row['ref_schema']}.{_quote(row['ref_table'])}.{_quote(row['ref_column'])}"
            fks.setdefault(key, []).append(fk)

        # Row counts (approximate, from pg_stat)
        cur.execute(
            """
            SELECT schemaname || '.' || relname AS table_key,
                   n_live_tup AS approx_rows
            FROM pg_stat_user_tables
            WHERE schemaname = ANY(%s)
            """,
            (list(schemas),),
        )
        row_counts = {r["table_key"]: r["approx_rows"] for r in cur.fetchall()}

        cur.close()

        # Build readable output
        tables: dict[str, list[dict]] = {}
        for col in columns:
            key = f"{col['table_schema']}.{col['table_name']}"
            tables.setdefault(key, []).append(col)

        lines: list[str] = []
        for table_key, cols in tables.items():
            count = row_counts.get(table_key, "?")
            schema_name, table_name = table_key.split(".", 1)
            quoted_table = f"{schema_name}.{_quote(table_name)}"
            lines.append(f"### {quoted_table} (~{count} rows)")
            pk_cols = pks.get(table_key, [])
            for c in cols:
                col_quoted = _quote(c["column_name"])
                nullable = "NULL" if c["is_nullable"] == "YES" else "NOT NULL"
                pk_mark = " [PK]" if col_quoted in pk_cols else ""
                default = f" DEFAULT {c['column_default']}" if c["column_default"] else ""
                lines.append(f"  - {col_quoted}: {c['data_type']} {nullable}{pk_mark}{default}")
            if table_key in fks:
                lines.append("  Foreign keys:")
                for fk in fks[table_key]:
                    lines.append(f"    - {fk}")
            lines.append("")

        return "\n".join(lines)

    def execute(self, sql: str) -> dict:
        """Execute a SQL statement and return structured results."""
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute(sql)
            if cur.description:
                columns = [desc.name for desc in cur.description]
                rows = [dict(row) for row in cur.fetchmany(500)]
                return {
                    "success": True,
                    "columns": columns,
                    "rows": rows,
                    "row_count": cur.rowcount,
                    "truncated": cur.rowcount > 500,
                }
            return {
                "success": True,
                "rows_affected": cur.rowcount,
            }
        except Exception as e:
            self.conn.rollback() if not self.conn.autocommit else None
            return {"success": False, "error": str(e)}
        finally:
            cur.close()
