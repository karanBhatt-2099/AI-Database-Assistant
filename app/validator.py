"""Static SQL safety layer. Defence in depth: this is layer 1 of 3
(1 validator, 2 read-only transaction + timeout, 3 SELECT-only DB role)."""
import os
import sqlglot
from sqlglot import exp

MAX_ROWS = int(os.getenv("MAX_ROWS", "500"))
ALLOWED_TABLES = {"regions", "customers", "products", "orders", "order_items"}
BLOCKED_FUNCS = {"set_config", "current_setting", "dblink", "query_to_xml", "xpath", "version",
                 "current_user", "session_user", "current_database"}
_FORBIDDEN = ["Insert", "Update", "Delete", "Drop", "Create", "Alter", "AlterTable", "Command", "Into",
              "Merge", "Copy", "Lock", "TruncateTable", "Set", "Use", "Transaction", "Commit", "Rollback",
              "Grant", "Pragma", "Execute"]
FORBIDDEN_NODES = tuple(getattr(exp, n) for n in _FORBIDDEN if hasattr(exp, n))


class UnsafeQuery(Exception):
    pass


def validate(sql: str) -> str:
    """Return a safe, row-capped SELECT or raise UnsafeQuery."""
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise UnsafeQuery("Empty query.")
    if len(sql) > 4000:
        raise UnsafeQuery("Query too long.")
    if "--" in sql or "/*" in sql:
        raise UnsafeQuery("SQL comments are not allowed.")
    try:
        stmts = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.SqlglotError as e:
        raise UnsafeQuery(f"Could not parse SQL: {str(e)[:150]}")
    if len(stmts) != 1:
        raise UnsafeQuery("Exactly one statement is allowed.")
    tree = stmts[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Subquery)):
        raise UnsafeQuery("Only SELECT queries are allowed.")
    bad = tree.find(*FORBIDDEN_NODES)
    if bad is not None:
        raise UnsafeQuery(f"Forbidden operation: {type(bad).__name__.upper()}.")
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for t in tree.find_all(exp.Table):
        if t.db and t.db.lower() != "public":
            raise UnsafeQuery(f"Schema '{t.db}' is not accessible.")
        name = t.name.lower()
        if name not in ALLOWED_TABLES and name not in ctes:
            raise UnsafeQuery(f"Table '{t.name}' is not in the allowed schema.")
    for f in tree.find_all(exp.Func):
        name = (f.name if isinstance(f, exp.Anonymous) else f.sql_name()).lower()
        if name in BLOCKED_FUNCS or name.startswith(("pg_", "lo_", "dblink")):
            raise UnsafeQuery(f"Function '{name}' is not allowed.")
    # always cap result size, regardless of what the model wrote
    return f"SELECT * FROM ({tree.sql(dialect='postgres')}) AS _q LIMIT {MAX_ROWS}"
