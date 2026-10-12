import httpx  # async test client
import pytest  # fixtures

from app import main  # app under test
from app.config import settings  # to set the password


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "app_access_username", "tapan")  # configure the gate
    monkeypatch.setattr(settings, "app_access_password", "secret")
    main.app.dependency_overrides.clear()  # use the real auth dependency
    main.app.dependency_overrides[main.get_graph] = lambda: None  # no LLM needed for auth tests
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t")  # in-process client


async def login(c, password="secret", username="tapan"):
    return await c.post("/api/login", json={"username": username, "password": password})  # helper


async def test_api_requires_login(client):
    async with client as c:
        assert (await c.post("/api/sessions")).status_code == 401  # no token
        assert (await c.post("/api/sessions", headers={"Authorization": "Bearer fake"})).status_code == 401  # bad token
        assert (await c.post("/api/sessions/x/messages", json={"message": "hi"})).status_code == 401  # messages too
        assert (await c.get("/api/sessions/x/messages")).status_code == 401  # history too
        assert (await c.get("/health")).status_code == 200  # health stays public


async def test_wrong_password_rejected_and_right_one_works(client):
    async with client as c:
        assert (await login(c, "nope")).status_code == 401  # wrong password
        assert (await login(c, username="someone")).status_code == 401  # wrong username, right password
        token = (await login(c)).json()["token"]  # right password
        r = await c.get("/api/sessions/x/messages", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404  # got past auth (session simply doesn't exist)


async def test_unconfigured_credentials_fail_closed(client, monkeypatch):
    monkeypatch.setattr(settings, "app_access_username", None)  # no username set
    async with client as c:
        assert (await login(c, "anything")).status_code == 503  # nobody can log in


async def test_brute_force_is_rate_limited(client):
    async with client as c:
        for _ in range(5):
            await login(c, "bad")  # five failures
        assert (await login(c, "secret")).status_code == 429  # even the right password is blocked for now


async def test_chat_rate_limit(client):
    async with client as c:
        token = (await login(c)).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        codes = [(await c.get("/api/sessions/x/messages", headers=headers)).status_code for _ in range(31)]
        assert codes[0] == 404 and codes[-1] == 429  # the 31st call in a minute is refused
