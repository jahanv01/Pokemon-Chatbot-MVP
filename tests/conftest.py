import pytest  # fixture decorator

from app import auth  # token store and limiters
from app.pokeapi import client  # shared module-level client


@pytest.fixture(autouse=True)
def clear_cache():
    client._cache.clear()  # every test starts with an empty cache
    auth.TOKENS.clear()  # no leftover logins
    auth.failed_logins.hits.clear()  # no leftover failed attempts
    auth.chat_calls.hits.clear()  # no leftover request counts
