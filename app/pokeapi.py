import re  # regex for stripping unwanted characters
import time  # monotonic clock for cache expiry
import unicodedata  # to strip accents (Flabébé -> Flabebe)
from difflib import SequenceMatcher, get_close_matches  # fuzzy name matching

import httpx  # async HTTP client

from app.config import settings  # base url and cache ttl


class PokeAPIError(Exception):
    """Raised on network failures or 5xx responses from PokeAPI."""


def normalize_name(name: str) -> str:
    """Turn user spelling into a PokeAPI slug: 'Mr. Mime' -> 'mr-mime'."""
    name = name.strip().lower().replace("♀", "-f").replace("♂", "-m")  # gendered Nidoran symbols
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()  # drop accents
    name = re.sub(r"[.'’:]", "", name)  # remove punctuation PokeAPI omits
    name = re.sub(r"[\s_]+", "-", name)  # spaces become hyphens
    return re.sub(r"[^a-z0-9-]", "", name).strip("-")  # drop anything else


def clean_text(text: str) -> str:
    """Collapse PokeAPI's stray \n and \f characters into single spaces."""
    return re.sub(r"\s+", " ", text).strip()  # any whitespace run -> one space


def english(entries: list[dict], key: str) -> str:
    """Return the first English text under `key` from a multilingual entry list."""
    for entry in entries:  # walk every language entry
        if entry["language"]["name"] == "en":  # keep English only
            return clean_text(entry[key])  # tidy whitespace
    return ""  # nothing in English


class PokeAPIClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(base_url=settings.pokeapi_base_url, timeout=10)  # shared connection pool
        self._cache: dict[str, tuple[float, dict]] = {}  # url -> (expiry, data)

    async def get_json(self, path: str) -> dict | None:
        """GET a PokeAPI path; None on 404, PokeAPIError on network/5xx errors."""
        hit = self._cache.get(path)  # look for a cached copy
        if hit and hit[0] > time.monotonic():  # still fresh?
            return hit[1]  # serve it without touching the network
        try:
            resp = await self._http.get(f"/{path.strip('/')}")  # real request
        except httpx.HTTPError as exc:  # timeouts, DNS, connection errors
            raise PokeAPIError(f"Could not reach PokeAPI: {exc}") from exc
        if resp.status_code == 404:  # unknown resource
            self._cache[path] = (time.monotonic() + settings.not_found_ttl_seconds, None)  # remember the miss briefly
            return None
        if resp.status_code >= 500:  # PokeAPI itself is failing
            raise PokeAPIError(f"PokeAPI returned {resp.status_code}")
        resp.raise_for_status()  # surface any other unexpected 4xx
        data = resp.json()  # parse body
        self._cache[path] = (time.monotonic() + settings.cache_ttl_seconds, data)  # remember it
        return data

    async def suggest(self, kind: str, slug: str) -> tuple[str | None, list[str]]:
        """Fuzzy-match a misspelt slug: (auto-corrected name or None, candidate names)."""
        listing = await self.get_json(f"{kind}?limit=2000")  # full name list, cached after the first call
        names = [r["name"] for r in listing["results"]]  # just the slugs
        found = get_close_matches(slug, names, n=3, cutoff=0.7)  # best candidates, best first
        scores = [SequenceMatcher(None, slug, n).ratio() for n in found]  # their similarity scores
        clear_winner = bool(found) and scores[0] >= 0.8 and (len(found) == 1 or scores[0] - scores[1] >= 0.08)  # confident enough to auto-correct
        return (found[0] if clear_winner else None), found  # correction only when unambiguous

    async def get_pokemon(self, name: str) -> dict | None:
        """Fetch /pokemon/<slug>, falling back to the species' default form (e.g. deoxys)."""
        slug = normalize_name(name)  # clean the user's spelling
        data = await self.get_json(f"pokemon/{slug}")  # try the direct route
        if data:  # found straight away
            return data
        species = await self.get_json(f"pokemon-species/{slug}")  # species may exist without a plain /pokemon entry
        if not species:  # truly unknown
            return None
        default = next(v for v in species["varieties"] if v["is_default"])  # the default form
        return await self.get_json(f"pokemon/{default['pokemon']['name']}")  # e.g. deoxys-normal


client = PokeAPIClient()  # module-level singleton shared by all tools
