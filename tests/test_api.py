import httpx  # async test client
import pytest  # fixtures
import respx  # mocks httpx calls
from langchain_core.messages import AIMessage  # scripted replies

from app import main  # module under test
from app.graph import build_graph, run_config  # graph factory + thread config
from tests.fakes import FakeChatModel, mock_pokemon, tool_call  # scripted model + PokeAPI mock


@pytest.fixture
def make_client():
    main.SESSIONS.clear()  # isolate tests from each other

    def factory(script):
        graph = build_graph(FakeChatModel(script=script))  # graph with a scripted model
        main.app.dependency_overrides[main.get_graph] = lambda: graph  # swap in the test graph
        main.app.dependency_overrides[main.require_auth] = lambda: None  # these tests are about chat, not login
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t")  # in-process client

    yield factory
    main.app.dependency_overrides.clear()  # restore the real dependency


async def new_session(client) -> str:
    return (await client.post("/api/sessions")).json()["session_id"]  # helper: create a session


async def test_full_chat_flow(make_client):
    async with make_client([AIMessage("Pikachu is Electric.")]) as c:
        created = (await c.post("/api/sessions")).json()  # create session
        assert created["greeting"] == "Hey there, what’s up?"  # exact greeting
        sid = created["session_id"]
        reply = (await c.post(f"/api/sessions/{sid}/messages", json={"message": "What's a Pikachu?"})).json()  # chat
        assert reply == {"reply": "Pikachu is Electric.", "cards": []}  # reply shape
        history = (await c.get(f"/api/sessions/{sid}/messages")).json()  # read history back
        assert [m["role"] for m in history] == ["assistant", "user", "assistant"]  # greeting, question, answer


async def test_sessions_are_isolated(make_client):
    async with make_client([AIMessage("A reply")]) as c:
        a, b = await new_session(c), await new_session(c)  # two chats
        await c.post(f"/api/sessions/{a}/messages", json={"message": "only in A"})  # talk in A
        history_b = (await c.get(f"/api/sessions/{b}/messages")).json()  # read B
        assert all("only in A" not in m["content"] for m in history_b)  # nothing leaked


async def test_busy_session_returns_409(make_client):
    async with make_client([]) as c:
        sid = await new_session(c)
        async with main.SESSIONS[sid]:  # simulate a reply in progress
            r = await c.post(f"/api/sessions/{sid}/messages", json={"message": "hi"})
        assert r.status_code == 409  # rejected while busy


async def test_validation_and_unknown_session(make_client):
    async with make_client([]) as c:
        sid = await new_session(c)
        assert (await c.post(f"/api/sessions/{sid}/messages", json={"message": "  "})).status_code == 422  # empty
        assert (await c.post(f"/api/sessions/{sid}/messages", json={"message": "x" * 1001})).status_code == 422  # too long
        assert (await c.post("/api/sessions/nope/messages", json={"message": "hi"})).status_code == 404  # unknown session
        assert (await c.get("/api/sessions/nope/messages")).status_code == 404  # unknown history


async def test_llm_failure_returns_502(make_client):
    async with make_client([]) as c:  # empty script makes the fake model raise
        sid = await new_session(c)
        r = await c.post(f"/api/sessions/{sid}/messages", json={"message": "hi"})
        assert r.status_code == 502 and "try again" in r.json()["detail"]  # friendly message
        assert not main.SESSIONS[sid].locked()  # lock released after failure


async def test_index_page_served(make_client):
    async with make_client([]) as c:
        r = await c.get("/")  # fetch the chat page
        assert r.status_code == 200 and "Pokémon Chatbot" in r.text  # page is served


@respx.mock
async def test_comparison_returns_two_cards(make_client):
    mock_pokemon("pikachu", 25, ["electric"], 35)  # fake PokeAPI data
    mock_pokemon("charizard", 6, ["fire", "flying"], 78)
    both = AIMessage(content="", tool_calls=[{"name": "get_pokemon", "args": {"name": n}, "id": n} for n in ("pikachu", "charizard")])  # two lookups at once
    async with make_client([both, AIMessage("Compared!")]) as c:
        sid = await new_session(c)
        data = (await c.post(f"/api/sessions/{sid}/messages", json={"message": "Pikachu vs Charizard"})).json()
        assert data["reply"] == "Compared!" and [card["name"] for card in data["cards"]] == ["pikachu", "charizard"]  # two cards


async def test_missing_api_key_gives_friendly_503(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)  # no key available
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)  # alternate name Gemini also accepts
    main.get_graph.cache_clear()  # force a rebuild
    main.app.dependency_overrides.clear()  # use the real graph factory
    main.app.dependency_overrides[main.require_auth] = lambda: None  # but skip login here
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as c:
        r = await c.post("/api/sessions")  # needs the graph
    assert r.status_code == 503 and "API key" in r.json()["detail"]  # friendly, not a raw 500


@respx.mock
async def test_failed_turn_is_rolled_back_and_retry_works(make_client):
    mock_pokemon("pikachu", 25, ["electric"], 35)  # fake PokeAPI data
    model = FakeChatModel(script=[tool_call("get_pokemon", {"name": "pikachu"})])  # tool call recorded, then the model "fails"
    graph = build_graph(model)  # graph we can inspect
    async with make_client([]) as c:
        main.app.dependency_overrides[main.get_graph] = lambda: graph  # use our graph instead
        sid = await new_session(c)
        r = await c.post(f"/api/sessions/{sid}/messages", json={"message": "What's a Pikachu?"})  # fails after the tool ran
        assert r.status_code == 502  # friendly error
        stored = (await graph.aget_state(run_config(sid))).values["messages"]  # history after the failure
        assert [m.content for m in stored] == ["Hey there, what’s up?"]  # half-finished turn was removed
        model.script.extend([tool_call("get_pokemon", {"name": "pikachu"}), AIMessage("Pikachu is Electric.")])  # model recovers
        r = await c.post(f"/api/sessions/{sid}/messages", json={"message": "What's a Pikachu?"})  # retry
        assert r.status_code == 200 and r.json()["reply"] == "Pikachu is Electric."  # works
        final = (await graph.aget_state(run_config(sid))).values["messages"]
        assert sum(m.type == "human" for m in final) == 1  # the question is stored once, not duplicated
