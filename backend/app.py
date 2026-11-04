"""FastAPI app: session API, streaming turns (SSE), and the static frontend."""
import asyncio
import contextlib
import json
import logging

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, store
from .agent import BudgetExceeded, Submission, run_turn
from .core.view import build_view, pending_tool_uses
from .dictation import dictation
from .llm import LLM

log = logging.getLogger("educator")


@contextlib.asynccontextmanager
async def lifespan(_app):
    dictation.prewarm()  # loads (and on first run downloads) the Whisper model in the background
    yield


app = FastAPI(title="Personal Educator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")

_llm: LLM | None = None
_locks: dict[str, asyncio.Lock] = {}
_tasks: set[asyncio.Task] = set()


def get_llm():
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm


def set_llm(llm) -> None:
    """Used by tests to swap in a fake model."""
    global _llm
    _llm = llm


def _status(s: dict) -> str:
    lock = _locks.get(s["id"])
    if lock and lock.locked():
        return "working"
    return "waiting" if pending_tool_uses(s) else "idle"


def _summary(s: dict) -> dict:
    return {"id": s["id"], "title": s["title"], "updated_at": s["updated_at"], "phase": s["phase"],
            "status": _status(s), "cost": s["usage"]["cost"]}


@app.get("/")
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")


@app.get("/api/sessions")
def sessions():
    return [_summary(s) for s in store.list_sessions()]


class NewSession(BaseModel):
    topic: str
    model: str | None = None
    effort: str | None = None


@app.post("/api/sessions")
def create_session(body: NewSession):
    st = store.load_settings()
    model = body.model if body.model in config.MODELS else st["teacher_model"]
    effort = body.effort if body.effort in config.EFFORTS else st["teacher_effort"]
    s = store.new_session(body.topic, model, effort)
    return _summary(s)


def _load(sid: str) -> dict:
    try:
        s = store.load_session(sid)
    except ValueError:
        s = None
    if not s:
        raise HTTPException(404, "session not found")
    return s


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    s = _load(sid)
    return {**_summary(s), "model": s["model"], "effort": s["effort"], "plan": s["plan"],
            "probe": s["probe"], "usage": s["usage"], **build_view(s)}


class SessionPatch(BaseModel):
    model: str | None = None
    effort: str | None = None
    title: str | None = None


@app.patch("/api/sessions/{sid}")
def patch_session(sid: str, body: SessionPatch):
    s = _load(sid)
    if body.model in config.MODELS:
        s["model"] = body.model
    if body.effort in config.EFFORTS:
        s["effort"] = body.effort
    if body.title and body.title.strip():
        s["title"] = body.title.strip()[:80]
    store.save_session(s)
    return _summary(s)


class Answer(BaseModel):
    choice: int | None = None
    idk: bool = False
    text: str = ""
    confidence: float | None = None
    thinking: str = ""


class Turn(BaseModel):
    answers: dict[str, Answer] = {}
    message: str = ""
    reading_thinking: str = ""


def _sse(evt: dict) -> str:
    return f"data: {json.dumps(evt)}\n\n"


@app.post("/api/sessions/{sid}/turn")
async def turn(sid: str, body: Turn):
    s = _load(sid)
    lock = _locks.setdefault(sid, asyncio.Lock())
    if lock.locked():
        raise HTTPException(409, "the teacher is still working on this session")

    sub = Submission(answers={k: v.model_dump() for k, v in body.answers.items()},
                     message=body.message, reading_thinking=body.reading_thinking)
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(evt: dict) -> None:
        await queue.put(evt)

    async def work():
        # Runs to completion even if the browser disconnects, so the session is always saved.
        async with lock:
            try:
                await run_turn(s, sub, get_llm(), emit)
            except BudgetExceeded as e:
                await emit({"type": "error", "message": str(e)})
            except anthropic.AuthenticationError:
                await emit({"type": "error", "message": "Claude rejected the API key (ANTHROPIC_API_KEY)."})
            except anthropic.RateLimitError:
                await emit({"type": "error", "message": "Rate limited by Claude. Wait a minute and resend."})
            except anthropic.APIStatusError as e:
                log.exception("API error")
                await emit({"type": "error", "message": f"Claude API error {e.status_code}: {e.message}"})
            except anthropic.APIConnectionError:
                await emit({"type": "error", "message": "Couldn't reach Claude. Check your internet."})
            except Exception as e:  # keep the stream alive and report
                log.exception("turn failed")
                await emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
            finally:
                await emit({"type": "done"})

    task = asyncio.create_task(work())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)

    async def stream():
        while True:
            evt = await queue.get()
            yield _sse(evt)
            if evt["type"] == "done":
                break

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---- voice input ----

@app.post("/api/dictation/start")
def dictation_start():
    try:
        dictation.start()
    except Exception as e:
        raise HTTPException(500, f"Couldn't open the microphone: {e}. On a Mac, allow microphone access "
                                 "in System Settings → Privacy & Security → Microphone.")
    return {"recording": True}


@app.get("/api/dictation/live")
def dictation_live():
    return {"recording": dictation.recording, "level": dictation.level, "text": dictation.live_text}


@app.post("/api/dictation/stop")
async def dictation_stop():
    return await asyncio.to_thread(dictation.stop)


@app.post("/api/dictation/polish/{take}")
async def dictation_polish(take: int):
    try:
        text = await asyncio.to_thread(dictation.polish, take)
    except Exception as e:
        log.exception("polish failed")
        raise HTTPException(500, f"Transcription failed: {e}")
    return {"text": text}


@app.post("/api/dictation/cancel")
def dictation_cancel():
    dictation.cancel()
    return {"recording": False}


@app.post("/api/client-log")
def client_log(body: dict):
    log.error("page error: %s", str(body.get("msg", ""))[:2000])
    return {"ok": True}


@app.get("/api/usage")
def usage():
    st = store.load_settings()
    return {"month_cost": store.month_cost(), "budget": st["monthly_budget_usd"]}


@app.get("/api/settings")
def get_settings():
    return {**store.load_settings(), "models": config.MODELS, "efforts": config.EFFORTS}


@app.put("/api/settings")
def put_settings(body: dict):
    st = store.load_settings()
    if body.get("teacher_model") in config.MODELS:
        st["teacher_model"] = body["teacher_model"]
    if body.get("teacher_effort") in config.EFFORTS:
        st["teacher_effort"] = body["teacher_effort"]
    b = body.get("monthly_budget_usd")
    if isinstance(b, (int, float)) and b >= 0:
        st["monthly_budget_usd"] = float(b)
    store.save_settings(st)
    return st


@app.get("/api/profile")
def get_profile():
    return store.load_profile()


@app.put("/api/profile")
def put_profile(body: dict):
    store.save_profile(body)
    return body
