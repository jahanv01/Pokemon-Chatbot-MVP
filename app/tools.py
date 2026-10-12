import json  # compact JSON text for the LLM
from collections import defaultdict  # multiplier table
from collections.abc import Awaitable, Callable  # type of the fetch functions

from langchain_core.tools import tool  # turns functions into LLM-callable tools

from app.pokeapi import client, english, normalize_name  # shared client + text helpers


def _dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))  # smallest JSON, keeps é


def _not_found(kind: str, name: str, options: list[str] | None = None) -> str:
    hint = f" Did you mean: {', '.join(options)}?" if options else ""  # suggestions when we have them
    return f"NOT_FOUND: there is no {kind} called '{name}'.{hint} Ask the user which one they meant."  # friendly hint for the LLM


async def _find(kind: str, name: str, fetch: Callable[[str], Awaitable[dict | None]]) -> tuple[dict | None, str]:
    data = await fetch(name)  # try the name as typed
    if data:  # exact hit
        return data, ""
    fixed, options = await client.suggest(kind, normalize_name(name))  # misspelt? look for close names
    if fixed:  # one clear winner
        return await fetch(fixed), f"'{name}' was auto-corrected to '{fixed}'. Mention this correction to the user."
    return None, _not_found(kind, name, options)  # unknown: no data, message for the LLM


async def _lookup(kind: str, name: str) -> tuple[dict | None, str]:
    return await _find(kind, name, lambda n: client.get_json(f"{kind}/{normalize_name(n)}"))  # generic /<kind>/<slug> lookup


def _how(details: list[dict]) -> list[dict]:
    keep = lambda v: v.get("name") if isinstance(v, dict) else v  # {"name": "thunder-stone"} -> "thunder-stone"
    return [{k: keep(v) for k, v in d.items() if v not in (None, "", False, [])} for d in details]  # drop empty requirements


def _paths(node: dict, prefix: tuple = ()) -> list[list[dict]]:
    stage = {"name": node["species"]["name"]}  # this evolution stage
    if node.get("evolution_details"):  # how this stage is reached (item, level, friendship, time...)
        stage["how"] = _how(node["evolution_details"])
    path = prefix + (stage,)  # extend the path with this stage
    if not node["evolves_to"]:  # end of a branch
        return [list(path)]  # one finished path
    return [p for child in node["evolves_to"] for p in _paths(child, path)]  # recurse (Eevee -> 8 paths)


@tool(response_format="content_and_artifact")  # returns (text for LLM, card for UI)
async def get_pokemon(name: str) -> tuple[str, dict | None]:
    """Look up a Pokémon by name: types, base stats, abilities, height, weight, category,
    description, generation, legendary status and evolution paths. Use for any question about a specific Pokémon."""
    data, note = await _find("pokemon", name, client.get_pokemon)  # /pokemon with form fallback + typo handling
    if not data:  # unknown Pokémon
        return note, None  # note holds the NOT_FOUND message; no card
    species = await client.get_json(f"pokemon-species/{data['species']['name']}")  # category, text, generation
    chain_path = species["evolution_chain"]["url"].split("/api/v2/")[1]  # full url -> relative path
    chain = await client.get_json(chain_path)  # evolution tree
    stats = {s["stat"]["name"]: s["base_stat"] for s in data["stats"]}  # stat name -> value
    stats["total"] = sum(stats.values())  # add the base stat total
    card = {
        "name": data["name"],  # display name source
        "id": data["id"],  # Pokédex number
        "category": english(species["genera"], "genus"),  # e.g. "Mouse Pokémon"
        "types": [t["type"]["name"] for t in data["types"]],  # for coloured badges
        "stats": {k: v for k, v in stats.items() if k != "total"},  # six base stats for the bars
        "image": data.get("sprites", {}).get("other", {}).get("official-artwork", {}).get("front_default"),  # official artwork url
        "source": f"https://pokeapi.co/api/v2/pokemon/{data['id']}",  # link back to the data
    }
    text = _dump({
        **({"note": note} if note else {}),  # tell the LLM about any auto-correction
        "name": data["name"],  # PokeAPI slug
        "id": data["id"],  # Pokédex number
        "types": [t["type"]["name"] for t in data["types"]],  # e.g. ["electric"]
        "stats": stats,  # base stats plus total
        "abilities": [{"name": a["ability"]["name"], "hidden": a["is_hidden"]} for a in data["abilities"]],  # hidden flagged
        "height_m": data["height"] / 10,  # decimetres -> metres
        "weight_kg": data["weight"] / 10,  # hectograms -> kilograms
        "category": english(species["genera"], "genus"),  # e.g. "Mouse Pokémon"
        "description": english(species["flavor_text_entries"], "flavor_text"),  # cleaned English text
        "generation": species["generation"]["name"],  # e.g. "generation-i"
        "legendary": species["is_legendary"] or species["is_mythical"],  # either special class
        "evolution_paths": _paths(chain["chain"]),  # flattened branches, each stage with how it evolves
    })
    return text, card  # LLM reads text, UI renders card


@tool
async def get_type_matchups(type_names: list[str]) -> str:
    """Get the damage matchups for one or two elemental types, with exact multipliers.
    For a dual-type Pokémon pass BOTH of its types in one call (e.g. ["fire", "flying"]) so combined
    weaknesses (4x, 2x), resistances (0.5x, 0.25x) and immunities are calculated correctly.
    Use for any weakness/resistance/strength question."""
    if not type_names:  # nothing to look up
        return _not_found("type", "")
    found = [await _lookup("type", n) for n in type_names]  # (data, note) for each type
    for data, note in found:  # stop at the first unknown type
        if not data:
            return note  # NOT_FOUND message
    mult: dict[str, float] = defaultdict(lambda: 1.0)  # attacking type -> damage multiplier
    for data, _ in found:  # combine every defending type
        rel = data["damage_relations"]  # PokeAPI's relation table
        for key, factor in (("double_damage_from", 2), ("half_damage_from", 0.5), ("no_damage_from", 0)):
            for t in rel[key]:  # each attacking type named in this relation
                mult[t["name"]] *= factor  # multiply (0 stays 0)
    num = lambda v: int(v) if v == int(v) else v  # 4.0 -> 4, 0.25 stays
    note = " ".join(n for _, n in found if n)  # any auto-correction notices
    return _dump({
        **({"note": note} if note else {}),  # tell the LLM about corrections
        "types": [d["name"] for d, _ in found],  # canonical names
        "weak_to": {k: num(v) for k, v in sorted(mult.items(), key=lambda kv: -kv[1]) if v > 1},  # e.g. {"rock":4,"water":2}
        "resists": {k: num(v) for k, v in sorted(mult.items(), key=lambda kv: kv[1]) if 0 < v < 1},  # e.g. {"grass":0.25}
        "immune_to": sorted(k for k, v in mult.items() if v == 0),  # takes no damage
        "super_effective_against": sorted({t["name"] for d, _ in found for t in d["damage_relations"]["double_damage_to"]}),  # what these types hit hard
    })


@tool
async def get_move(name: str) -> str:
    """Look up a Pokémon move (e.g. thunderbolt): type, power, accuracy, PP, category and effect."""
    data, note = await _lookup("move", name)  # /move/<slug>
    if not data:  # unknown move
        return note  # NOT_FOUND message
    effect = english(data["effect_entries"], "short_effect")  # English effect text
    effect = effect.replace("$effect_chance", str(data["effect_chance"]))  # fill the placeholder
    return _dump({
        **({"note": note} if note else {}),  # auto-correction notice
        "name": data["name"],  # canonical move name
        "type": data["type"]["name"],  # elemental type
        "power": data["power"],  # None for status moves
        "accuracy": data["accuracy"],  # None if it never misses
        "pp": data["pp"],  # power points
        "category": data["damage_class"]["name"],  # physical / special / status
        "effect": effect,  # readable effect
        "effect_chance_percent": data["effect_chance"],  # e.g. 10 (the effect text may not repeat it)
    })


@tool
async def get_ability(name: str) -> str:
    """Look up a Pokémon ability (e.g. static): what it does and some example Pokémon that have it."""
    data, note = await _lookup("ability", name)  # /ability/<slug>
    if not data:  # unknown ability
        return note  # NOT_FOUND message
    return _dump({
        **({"note": note} if note else {}),  # auto-correction notice
        "name": data["name"],  # canonical ability name
        "effect": english(data["effect_entries"], "short_effect"),  # English effect text
        "example_pokemon": [p["pokemon"]["name"] for p in data["pokemon"][:5]],  # first five holders
    })


TOOLS = [get_pokemon, get_type_matchups, get_move, get_ability]  # list handed to the agent graph
