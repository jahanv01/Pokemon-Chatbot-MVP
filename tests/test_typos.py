import json  # parse tool output

import respx  # mocks httpx calls

from app.tools import get_pokemon  # code under test
from tests.test_tools import API, mock_pikachu  # shared PokeAPI mock


def mock_names(*names: str) -> None:
    respx.get(API + "pokemon?limit=2000").respond(json={"results": [{"name": n} for n in names]})  # fake name list


@respx.mock
async def test_clear_typo_is_auto_corrected():
    mock_names("pikachu", "pichu", "raichu")  # candidates
    respx.get(API + "pokemon/pikachoo").respond(404)  # typo misses
    respx.get(API + "pokemon-species/pikachoo").respond(404)
    mock_pikachu()  # corrected name resolves
    out = json.loads(await get_pokemon.ainvoke({"name": "Pikachoo"}))  # score is exactly 0.8
    assert out["name"] == "pikachu" and "auto-corrected" in out["note"]  # corrected and flagged for the LLM


@respx.mock
async def test_ambiguous_typo_returns_suggestions():
    mock_names("charmander", "charmeleon", "charizard")  # two equally close names
    respx.get(API + "pokemon/charmelder").respond(404)  # typo misses
    respx.get(API + "pokemon-species/charmelder").respond(404)
    out = await get_pokemon.ainvoke({"name": "charmelder"})  # tie: 0.8 vs 0.8
    assert out.startswith("NOT_FOUND") and "charmander" in out and "charmeleon" in out  # asks "did you mean"


@respx.mock
async def test_unknown_name_has_no_suggestions_and_miss_is_cached():
    mock_names("pikachu")  # nothing close to the input
    miss = respx.get(API + "pokemon/zzzzzz").respond(404)  # count how often it is hit
    respx.get(API + "pokemon-species/zzzzzz").respond(404)
    first = await get_pokemon.ainvoke({"name": "zzzzzz"})  # first lookup
    await get_pokemon.ainvoke({"name": "zzzzzz"})  # repeat lookup
    assert first.startswith("NOT_FOUND") and "Did you mean" not in first  # plain not-found
    assert miss.call_count == 1  # the 404 was cached
