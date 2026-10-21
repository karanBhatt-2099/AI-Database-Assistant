# AI Database Assistant

Ask questions about a PostgreSQL database in plain English. An LLM turns each question into SQL; the SQL is
validated, executed read-only, and the result comes back as a short explanation, a table, and (when useful) a chart.

**Live demo:** `<paste Render URL>` · **Video:** `<paste link>`

## Quick start (local, ~3 min)

```bash
cp .env.example .env          # add GROQ_API_KEY
docker compose up -d db
pip install -r requirements.txt
set -a; . ./.env; set +a
python -m db.seed             # schema + synthetic data + readonly_user role
uvicorn app.main:app --reload # http://localhost:8000
python -m pytest tests -q     # validator unit tests (no DB / key needed)
python tests/eval.py          # end-to-end eval, writes docs/EVAL_RESULTS.md
```
Or all-in-Docker: `docker compose up --build` then `docker compose exec app python -m db.seed`.

## Deploy (free tier)
1. Create a free Postgres on **Neon** (or Render). Run `ADMIN_DATABASE_URL=<admin url> READONLY_PASSWORD=<pw> python -m db.seed` once from your laptop.
2. Push to GitHub → Render → *New Blueprint* (uses `render.yaml`). Set `DATABASE_URL` to the **readonly_user** URL and `GROQ_API_KEY`.
3. The web service never sees the admin credentials.

## Architecture
```
Browser (chat + Chart.js)
   │  POST /api/chat {question, last ≤6 turns}
FastAPI ── 1. LLM plan (forced tool call → {status: sql|clarify|unanswerable, sql, chart})
        ── 2. validator.py  (sqlglot AST checks)  ──fail──► 3. one LLM self-repair retry with the error
        ── 4. db.py  READ ONLY txn + statement_timeout, as SELECT-only role
        ── 5. LLM explanation (sees ≤20 result rows)
   ▼
PostgreSQL (regions, customers, products, orders, order_items)
```
**Schema grounding:** table/column/FK info and low-cardinality values (e.g. region names, statuses) are read from
`information_schema` at startup and put in the prompt, plus explicit business rules (revenue = completed orders only).

**Security — three independent layers**
| Layer | What it stops |
|---|---|
| `validator.py` (AST, not regex) | non-SELECT, multi-statement, `SELECT INTO`, `FOR UPDATE`, comments, tables outside the 5 allowed, other schemas (`pg_catalog`, `information_schema`), dangerous functions (`pg_*`, `set_config`, `dblink`…), forces `LIMIT 500` |
| Read-only transaction + 5 s `statement_timeout` | anything that slipped through that writes, runaway queries |
| `readonly_user` (GRANT SELECT only, no CREATE, `default_transaction_read_only=on`) | final backstop at the database itself |

Also: input length limits, per-IP rate limit (20/min), prompt-injection stance (question = data), generic error messages (no stack traces), no secrets in repo.

**Failure behaviour:** vague question → `clarify` (asks one question); unrelated/write/system requests → `unanswerable` or `refused`;
invalid SQL → one repair retry, then a clear message.

## Model / provider choices
- **`openai/gpt-oss-120b` on Groq** (free tier, OpenAI-compatible API; change with `LLM_MODEL`). Strong at SQL, fast inference, $0 for this MVP. Forced tool-calling returns structured JSON (`status`, `sql`, `chart`) without parsing hacks.
- **FastAPI + psycopg3 + sqlglot**: small and typed; sqlglot gives a real Postgres parser for validation.
- **Neon Postgres (free) + Render web service (free).** Single-file static UI, no build step.

## Cost (approx.)
Free: Groq free tier + Neon free + Render free. At paid rates a question uses ~3k input and ~0.5k output tokens across two LLM calls, i.e. well under $0.01. Limits: Groq free-tier rate limits, Render cold start (~30 s) after idle.

## Limitations (honest list)
- Single-database, fixed 5-table allow-list; no auth or per-user quotas (in-memory rate limit resets on restart).
- LLM can still write a *valid but wrong* query (e.g. a different definition of "sales"). Mitigations: business rules in the prompt, SQL shown to the user, eval against reference SQL. Not a guarantee.
- Explanation sees only the first 20 rows; large results are summarised from that sample.
- Follow-up context is just the last few chat turns; no long-term memory.
- Not implemented: streaming responses, query result caching, row-level security.

## Testing evidence
- `tests/test_validator.py`: 21 cases (5 safe, 16 attack/malformed) — all pass, no DB needed.
- `tests/eval.py`: 12 end-to-end cases (2 demo scenarios checked against reference SQL, 3 unfamiliar queries, 1 ambiguity, 6 refusal/injection cases). Run it against your deployment and commit `docs/EVAL_RESULTS.md` as evidence together with the metrics it prints (pass-rate, mean/p95 latency, tokens).
- DB-level check: `psql "$DATABASE_URL" -c "DELETE FROM orders"` → `permission denied` / `read-only transaction`.

## Demo script (5 min)
1. "Which products generated the most revenue?" → table + bar chart, open *SQL used*.
2. "How did monthly sales change across regions?" → multi-line chart.
3. Unfamiliar: "Which customers bought from more than 3 categories?"
4. Ambiguity: "Show me the best ones" → clarifying question.
5. Safety: "Delete all cancelled orders" → refused; show the validator tests and the DB permission error.
6. Walk through architecture + limitations.