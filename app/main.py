import asyncio  # per-session locks
import logging  # so server errors show in the terminal
import uuid  # session ids
from functools import lru_cache  # build the graph once, lazily
from pathlib import Path  # locate the static folder
from typing import Annotated  # constrained string type

from fastapi import Depends, FastAPI, HTTPException  # web framework pieces
from fastapi.responses import FileResponse  # serve the chat page
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage  # message types
from pydantic import BaseModel, StringConstraints  # request validation

from app.auth import require_auth, router as auth_router  # login + token check
from app.config import settings  # message length limit
from app.graph import GREETING, build_graph, run_config, start_session  # agent graph

log = logging.getLogger("uvicorn.error")  # same stream uvicorn prints to
app = FastAPI(title="Pokémon Chatbot")  # the ASGI app uvicorn serves
app.include_router(auth_router)  # adds POST /api/login
SESSIONS: dict[str, asyncio.Lock] = {}  # session id -> lock that blocks overlapping messages


class MessageIn(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=settings.max_message_chars)]  # 1-1000 chars, else 422


async def rollback(graph, config: dict, keep: int) -> None:
    try:
        messages = (await graph.aget_state(config)).values["messages"]  # what is stored now
        extra = [RemoveMessage(id=m.id) for m in messages[keep:]]  # everything this failed turn added
        if extra:  # only touch the state if something was left behind
            await graph.aupdate_state(config, {"messages": extra}, as_node="agent")  # restore history; as_node clears pending steps
    except Exception:  # never let cleanup hide the original error
        log.exception("Could not roll back the failed turn")


@lru_cache
def get_graph():
    try:
        return build_graph()  # lazy so /health works without an API key
    except Exception as exc:  # most often: missing API key or bad LLM_MODEL
        raise HTTPException(503, "The chatbot isn't configured yet: set your LLM API key in .env (see README).") from exc


@app.get("/health")
async def health():
    return {"status": "ok"}  # liveness check


@app.post("/api/sessions", dependencies=[Depends(require_auth)])
async def create_session(graph=Depends(get_graph)):
    session_id = uuid.uuid4().hex  # unguessable id
    await start_session(graph, session_id)  # store the greeting in history
    SESSIONS[session_id] = asyncio.Lock()  # register the session
    return {"session_id": session_id, "greeting": GREETING}


@app.post("/api/sessions/{session_id}/messages", dependencies=[Depends(require_auth)])
async def send_message(session_id: str, body: MessageIn, graph=Depends(get_graph)):
    lock = SESSIONS.get(session_id)  # find the session's lock
    if lock is None:  # unknown session
        raise HTTPException(404, "Session not found.")
    if lock.locked():  # a reply is still being generated
        raise HTTPException(409, "Still working on the previous answer.")
    async with lock:  # block other messages for this session
        config = run_config(session_id)  # thread id + recursion limit
        before = len((await graph.aget_state(config)).values["messages"])  # messages already stored
        try:
            result = await graph.ainvoke({"messages": [HumanMessage(body.message)]}, config)  # run the agent
        except Exception as exc:  # LLM down, bad key, recursion limit...
            log.exception("Chat turn failed")  # keep the real cause visible to the developer
            await rollback(graph, config, before)  # drop half-finished messages so a retry starts clean
            raise HTTPException(502, "Sorry, I couldn't get an answer right now. Please try again.") from exc
    new = result["messages"][before:]  # only this turn's messages
    cards = [m.artifact for m in new if isinstance(m, ToolMessage) and m.artifact]  # UI cards from tool results
    return {"reply": result["messages"][-1].text, "cards": cards}


@app.get("/api/sessions/{session_id}/messages", dependencies=[Depends(require_auth)])
async def get_messages(session_id: str, graph=Depends(get_graph)):
    if session_id not in SESSIONS:  # unknown session
        raise HTTPException(404, "Session not found.")
    messages = (await graph.aget_state(run_config(session_id))).values["messages"]  # full history
    roles = {HumanMessage: "user", AIMessage: "assistant"}  # visible message types
    return [{"role": roles[type(m)], "content": m.text} for m in messages if type(m) in roles and m.text]  # hide tool plumbing


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")  # the chat page
