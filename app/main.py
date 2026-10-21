import os, time, json, logging, collections
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, llm
from .validator import validate, UnsafeQuery

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("assistant")
app = FastAPI(title="AI Database Assistant")
STATIC = Path(__file__).parent / "static"
RATE = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))
_hits: dict = collections.defaultdict(collections.deque)
_schema_cache = {"text": None}


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=1000)


class ChatIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    history: list[Turn] = Field(default_factory=list, max_length=6)


def schema_text():
    if not _schema_cache["text"]:
        _schema_cache["text"] = db.describe_schema()
    return _schema_cache["text"]


def rate_limit(ip):
    q, now = _hits[ip], time.time()
    while q and now - q[0] > 60: q.popleft()
    if len(q) >= RATE:
        raise HTTPException(429, "Too many requests. Try again in a minute.")
    q.append(now)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/schema")
def schema():
    return {"schema": schema_text()}


@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    rate_limit(request.client.host if request.client else "?")
    t0, tin, tout, sql, feedback = time.time(), 0, 0, None, None
    try:
        schema = schema_text()
        for attempts in (1, 2):                      # one self-repair retry
            p, i, o = llm.plan(schema, body.question, [h.model_dump() for h in body.history], feedback)
            tin, tout = tin + i, tout + o
            if p["status"] != "sql":
                return _done(body, t0, tin, tout, attempts, status=p["status"], sql=None,
                             message=p.get("message") or "I can't answer that from this database.")
            try:
                sql = p.get("sql", "")
                cols, rows = db.run(validate(sql))
                break
            except (UnsafeQuery, db.DBError) as e:
                feedback = (sql, str(e))
                if attempts == 2:
                    kind = "refused" if isinstance(e, UnsafeQuery) else "error"
                    return _done(body, t0, tin, tout, attempts, status=kind, sql=sql,
                                 message=f"I couldn't produce a safe, valid query ({e}). Try rephrasing.")
        text, i, o = llm.explain(body.question, cols, rows, len(rows))
        tin, tout = tin + i, tout + o
        chart = p.get("chart") or {"type": "none"}
        if chart.get("type") != "none" and not (chart.get("x") in cols and chart.get("y") in cols):
            chart = {"type": "none"}
        return _done(body, t0, tin, tout, attempts, status="ok", sql=sql, message=text,
                     columns=cols, rows=rows, chart=chart)
    except HTTPException:
        raise
    except Exception as e:  # never leak internals
        log.error(json.dumps({"event": "error", "err": repr(e)[:300]}))
        return JSONResponse({"status": "error", "message": "Something went wrong. Please try again."}, 500)


def _done(body, t0, tin, tout, attempts, **kw):
    out = {"latency_ms": int((time.time() - t0) * 1000), "attempts": attempts,
           "tokens_in": tin, "tokens_out": tout, **kw}
    log.info(json.dumps({"event": "chat", "q": body.question[:120], "status": kw["status"],
                         "latency_ms": out["latency_ms"], "attempts": attempts, "tokens": tin + tout}))
    return out


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
