import json  # parse tool output

import respx  # mocks httpx calls

from app.tools import _paths, get_ability, get_move, get_pokemon, get_type_matchups  # code under test

API = "https://pokeapi.co/api/v2/"  # base url used in mocks


def mock_pikachu():
    respx.get(API + "pokemon/pikachu").respond(json={  # minimal /pokemon payload
        "name": "pikachu", "id": 25, "height": 4, "weight": 60, "species": {"name": "pikachu"},
        "types": [{"type": {"name": "electric"}}],
        "stats": [{"stat": {"name": "hp"}, "base_stat": 35}, {"stat": {"name": "speed"}, "base_stat": 90}],
        "abilities": [{"ability": {"name": "static"}, "is_hidden": False}, {"ability": {"name": "lightning-rod"}, "is_hidden": True}]})
    respx.get(API + "pokemon-species/pikachu").respond(json={  # minimal /pokemon-species payload
        "genera": [{"language": {"name": "en"}, "genus": "Mouse Pokémon"}],
        "flavor_text_entries": [{"language": {"name": "en"}, "flavor_text": "Stores\nelectricity\fin cheeks."}],
        "generation": {"name": "generation-i"}, "is_legendary": False, "is_mythical": False,
        "evolution_chain": {"url": API + "evolution-chain/10/"}})
    respx.get(API + "evolution-chain/10").respond(json={"chain": {  # pichu -> pikachu -> raichu
        "species": {"name": "pichu"}, "evolution_details": [], "evolves_to": [
            {"species": {"name": "pikachu"}, "evolution_details": [{"trigger": {"name": "level-up"}, "min_happiness": 220, "item": None, "min_level": None, "time_of_day": ""}],
             "evolves_to": [{"species": {"name": "raichu"}, "evolves_to": [], "evolution_details": [
                 {"trigger": {"name": "use-item"}, "item": {"name": "thunder-stone"}, "min_happiness": None}]}]}]}})


@respx.mock
async def test_get_pokemon_happy_path():
    mock_pikachu()  # register the three endpoints
    out = json.loads(await get_pokemon.ainvoke({"name": "Pikachu"}))  # call the tool
    assert out["types"] == ["electric"] and out["stats"]["total"] == 125  # types + stat total
    assert out["height_m"] == 0.4 and out["weight_kg"] == 6.0  # unit conversion
    assert out["description"] == "Stores electricity in cheeks."  # whitespace cleaned
    assert out["abilities"][1] == {"name": "lightning-rod", "hidden": True}  # hidden flagged
    assert out["evolution_paths"] == [[  # flattened chain, with how each stage is reached
        {"name": "pichu"},
        {"name": "pikachu", "how": [{"trigger": "level-up", "min_happiness": 220}]},
        {"name": "raichu", "how": [{"trigger": "use-item", "item": "thunder-stone"}]}]]


def test_eevee_branches_flatten():
    eevee = {"species": {"name": "eevee"}, "evolves_to": [{"species": {"name": f"e{i}"}, "evolves_to": []} for i in range(8)]}  # 8 branches
    assert len(_paths(eevee)) == 8  # one path per eeveelution


@respx.mock
async def test_type_matchups():
    respx.get(API + "type/electric").respond(json={"name": "electric", "damage_relations": {
        "double_damage_from": [{"name": "ground"}], "half_damage_from": [{"name": "flying"}],
        "no_damage_from": [], "double_damage_to": [{"name": "water"}]}})  # electric table
    out = json.loads(await get_type_matchups.ainvoke({"type_names": ["Electric"]}))  # call the tool
    assert out["weak_to"] == {"ground": 2} and out["super_effective_against"] == ["water"]  # relations mapped


@respx.mock
async def test_move_effect_chance_replaced():
    respx.get(API + "move/thunderbolt").respond(json={
        "name": "thunderbolt", "type": {"name": "electric"}, "power": 90, "accuracy": 100, "pp": 15,
        "damage_class": {"name": "special"}, "effect_chance": 10,
        "effect_entries": [{"language": {"name": "en"}, "short_effect": "Has a $effect_chance% chance to paralyze."}]})
    out = json.loads(await get_move.ainvoke({"name": "thunderbolt"}))  # call the tool
    assert out["effect"] == "Has a 10% chance to paralyze." and out["power"] == 90  # placeholder filled
    assert out["effect_chance_percent"] == 10  # chance also given as its own field


@respx.mock
async def test_ability():
    respx.get(API + "ability/static").respond(json={"name": "static", "pokemon": [{"pokemon": {"name": "pikachu"}}],
        "effect_entries": [{"language": {"name": "en"}, "short_effect": "May paralyze on contact."}]})
    out = json.loads(await get_ability.ainvoke({"name": "static"}))  # call the tool
    assert out["example_pokemon"] == ["pikachu"]  # example holders returned


@respx.mock
async def test_not_found_everywhere():
    for path in ["pokemon/xyz", "pokemon-species/xyz", "type/xyz", "move/xyz", "ability/xyz"]:
        respx.get(API + path).respond(404)  # everything missing
    for kind in ["pokemon", "type", "move", "ability"]:
        respx.get(API + f"{kind}?limit=2000").respond(json={"results": []})  # empty name lists, so no suggestions
    for tool, arg in [(get_pokemon, "name"), (get_type_matchups, "type_names"), (get_move, "name"), (get_ability, "name")]:
        assert (await tool.ainvoke({arg: ["xyz"] if arg == "type_names" else "xyz"})).startswith("NOT_FOUND")  # friendly message, no crash


@respx.mock
async def test_get_pokemon_returns_card_artifact():
    mock_pikachu()  # register the three endpoints
    msg = await get_pokemon.ainvoke({"type": "tool_call", "name": "get_pokemon", "args": {"name": "pikachu"}, "id": "1"})  # full tool call -> ToolMessage
    assert msg.artifact["types"] == ["electric"] and msg.artifact["id"] == 25  # card data rides along
    assert "total" not in msg.artifact["stats"] and msg.artifact["source"].endswith("/pokemon/25")  # six stats + source link


@respx.mock
async def test_dual_type_matchups_are_combined_in_code():
    ref = lambda *names: [{"name": n} for n in names]  # helper: PokeAPI type refs
    respx.get(API + "type/fire").respond(json={"name": "fire", "damage_relations": {
        "double_damage_from": ref("ground", "rock", "water"), "half_damage_from": ref("fire", "grass", "ice", "bug", "steel", "fairy"),
        "no_damage_from": [], "double_damage_to": ref("grass", "ice", "bug", "steel")}})
    respx.get(API + "type/flying").respond(json={"name": "flying", "damage_relations": {
        "double_damage_from": ref("rock", "electric", "ice"), "half_damage_from": ref("grass", "fighting", "bug"),
        "no_damage_from": ref("ground"), "double_damage_to": ref("grass", "fighting", "bug")}})
    out = json.loads(await get_type_matchups.ainvoke({"type_names": ["fire", "flying"]}))  # Charizard's types
    assert out["weak_to"] == {"rock": 4, "water": 2, "electric": 2}  # Rock is 4x; ice cancels out to neutral
    assert out["immune_to"] == ["ground"]  # Flying makes it immune to Ground (the bug the LLM made)
    assert out["resists"]["grass"] == 0.25 and out["resists"]["fire"] == 0.5  # stacked resistances
