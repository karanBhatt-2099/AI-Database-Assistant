import os, decimal, datetime
import psycopg

TIMEOUT = int(os.getenv("STATEMENT_TIMEOUT_MS", "5000"))


def _url():
    return os.environ["DATABASE_URL"]


class DBError(Exception):
    pass


def _json(v):
    if isinstance(v, decimal.Decimal): return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)): return v.isoformat()
    return v


def run(sql: str):
    """Execute inside a READ ONLY transaction with a timeout. Returns (columns, rows)."""
    try:
        with psycopg.connect(_url(), connect_timeout=5) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = {TIMEOUT}")
                cur.execute(sql)
                cols = [d.name for d in cur.description]
                rows = [[_json(v) for v in r] for r in cur.fetchall()]
        return cols, rows
    except psycopg.Error as e:
        raise DBError(str(e).split("\n")[0][:300])


def describe_schema() -> str:
    """Compact schema text (columns, FKs, low-cardinality values) for the prompt."""
    out = []
    with psycopg.connect(_url(), connect_timeout=5) as conn:
        conn.read_only = True
        tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1")]
        fks = {(r[0], r[1]): f"{r[2]}.{r[3]}" for r in conn.execute("""
            SELECT kcu.table_name, kcu.column_name, ccu.table_name, ccu.column_name
            FROM information_schema.key_column_usage kcu
            JOIN information_schema.referential_constraints rc USING (constraint_name)
            JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = rc.unique_constraint_name
            WHERE kcu.table_schema='public'""")}
        for t in tables:
            cols = conn.execute("SELECT column_name, data_type FROM information_schema.columns "
                                "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", (t,)).fetchall()
            parts = []
            for c, dtp in cols:
                s = f"{c} {dtp}"
                if (t, c) in fks: s += f" -> {fks[(t, c)]}"
                if dtp == "text" and c != "email":
                    vals = [r[0] for r in conn.execute(f'SELECT DISTINCT "{c}" FROM "{t}" LIMIT 13')]
                    if len(vals) <= 12: s += " values=" + str(vals)
                parts.append(s)
            out.append(f"TABLE {t}(" + "; ".join(parts) + ")")
    return "\n".join(out)
