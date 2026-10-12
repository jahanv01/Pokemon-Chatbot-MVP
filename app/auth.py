import secrets  # random tokens + constant-time compare
import time  # monotonic clock for expiry and rate windows
from collections import defaultdict  # per-key hit lists

from fastapi import APIRouter, Depends, HTTPException, Request  # web framework pieces
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # reads "Authorization: Bearer ..."
from pydantic import BaseModel  # login request body

from app.config import settings  # password and limits

router = APIRouter()  # holds the /api/login route
TOKENS: dict[str, float] = {}  # session token -> expiry time
bearer = HTTPBearer(auto_error=False)  # we raise our own 401 instead


class RateLimiter:
    def __init__(self, limit: int, window: float) -> None:
        self.limit, self.window = limit, window  # max events per time window
        self.hits: dict[str, list[float]] = defaultdict(list)  # key -> event times

    def allowed(self, key: str) -> bool:
        now = time.monotonic()  # current time
        self.hits[key] = [t for t in self.hits[key] if now - t < self.window]  # forget old events
        return len(self.hits[key]) < self.limit  # still under the limit?

    def record(self, key: str) -> None:
        self.hits[key].append(time.monotonic())  # count one event


failed_logins = RateLimiter(limit=5, window=300)  # 5 wrong passwords per 5 min per IP
chat_calls = RateLimiter(limit=30, window=60)  # 30 API calls per minute per token


class LoginIn(BaseModel):
    username: str  # login name the user typed
    password: str  # password the user typed


@router.post("/api/login")
async def login(body: LoginIn, request: Request):
    if not (settings.app_access_username and settings.app_access_password):  # fail closed when credentials are not configured
        raise HTTPException(503, "Access credentials are not configured on the server.")
    ip = request.client.host if request.client else "unknown"  # who is asking
    if not failed_logins.allowed(ip):  # too many wrong guesses
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    user_ok = secrets.compare_digest(body.username.encode(), settings.app_access_username.encode())  # constant-time username check
    pass_ok = secrets.compare_digest(body.password.encode(), settings.app_access_password.encode())  # constant-time password check
    if not (user_ok and pass_ok):  # both are always evaluated, so timing doesn't reveal which was wrong
        failed_logins.record(ip)  # remember the failure
        raise HTTPException(401, "Wrong username or password.")
    token = secrets.token_urlsafe(32)  # unguessable session token
    TOKENS[token] = time.monotonic() + settings.token_ttl_seconds  # valid until this time
    return {"token": token}


async def require_auth(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    token = creds.credentials if creds else ""  # token from the header, if any
    if TOKENS.get(token, 0) < time.monotonic():  # unknown or expired
        TOKENS.pop(token, None)  # clean up expired entries
        raise HTTPException(401, "Please log in.")
    if not chat_calls.allowed(token):  # too many requests from this login
        raise HTTPException(429, "You're sending requests too fast. Please slow down.")
    chat_calls.record(token)  # count this request
