import httpx  # for building mock responses
import pytest  # for pytest.raises
import respx  # mocks httpx calls

from app.pokeapi import PokeAPIClient, PokeAPIError, normalize_name  # code under test


@pytest.mark.parametrize("raw,slug", [("Mr. Mime", "mr-mime"), ("Farfetch'd", "farfetchd"), ("Nidoran♀", "nidoran-f"), ("  Pikachu ", "pikachu")])
def test_normalize_name(raw, slug):
    assert normalize_name(raw) == slug  # spelling maps to the PokeAPI slug


@respx.mock
async def test_cache_prevents_second_request():
    route = respx.get("https://pokeapi.co/api/v2/pokemon/pikachu").respond(json={"name": "pikachu"})  # mocked endpoint
    c = PokeAPIClient()  # fresh client with empty cache
    assert (await c.get_json("pokemon/pikachu"))["name"] == "pikachu"  # first call fetches
    await c.get_json("pokemon/pikachu")  # second call should be cached
    assert route.call_count == 1  # network hit exactly once


@respx.mock
async def test_404_none_and_5xx_error():
    respx.get("https://pokeapi.co/api/v2/pokemon/nope").respond(404)  # missing
    respx.get("https://pokeapi.co/api/v2/pokemon/boom").respond(503)  # server down
    c = PokeAPIClient()
    assert await c.get_json("pokemon/nope") is None  # 404 -> None
    with pytest.raises(PokeAPIError):  # 5xx -> custom error
        await c.get_json("pokemon/boom")


@respx.mock
async def test_species_form_fallback():
    respx.get("https://pokeapi.co/api/v2/pokemon/deoxys").respond(404)  # no plain entry
    respx.get("https://pokeapi.co/api/v2/pokemon-species/deoxys").respond(json={"varieties": [
        {"is_default": False, "pokemon": {"name": "deoxys-attack"}},
        {"is_default": True, "pokemon": {"name": "deoxys-normal"}}]})  # species lists forms
    respx.get("https://pokeapi.co/api/v2/pokemon/deoxys-normal").respond(json={"name": "deoxys-normal"})  # default form
    assert (await PokeAPIClient().get_pokemon("Deoxys"))["name"] == "deoxys-normal"  # fallback resolved
