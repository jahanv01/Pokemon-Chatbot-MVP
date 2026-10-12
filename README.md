# Pokémon Chatbot MVP

A web chatbot that answers Pokémon questions using data from [PokeAPI](https://pokeapi.co). It greets you, keeps the conversation history so follow-ups like "How's that different from a Charizard?" make sense, and can move from one Pokémon topic to another. Built with **LangGraph + FastAPI**, using a Gemini model (a free-tier key is enough to try it).

## Contents

1. [Overview and assignment requirements](#overview-and-assignment-requirements)
2. [Example conversation](#example-conversation)
3. [Three-minute evaluation walkthrough](#three-minute-evaluation-walkthrough)
4. [Supported topics and limitations](#supported-topics-and-limitations)
5. [Quick start](#quick-start-from-git-clone-to-running)
6. [Architecture and design decisions](#architecture-and-design-decisions)
7. [Testing and verification](#testing-and-verification)
8. [Configuration](#configuration-env)
9. [API reference](#api-reference)
10. [Privacy and session behaviour](#privacy-and-session-behaviour)
11. [Troubleshooting](#troubleshooting)
12. [Known limitations and next steps](#known-limitations-and-next-steps)

## Overview and assignment requirements

```
Browser UI ──► FastAPI (login, sessions, locks) ──► LangGraph agent (LLM ⇄ tools) ──► PokeAPI client (async httpx + cache)
```

| Requirement | How it is met |
|---|---|
| Greets every new chat with `Hey there, what’s up?` | The exact text is stored as the first message of each new session (covered by tests). |
| A response for every input; input may be blocked while generating | The UI disables the input, Send and New chat while a reply is generated. The API also returns 409 for an overlapping message in the same session. Errors return a friendly message instead of silence. |
| Responses use the full conversation context and implicit references | The whole history is sent to the model on every turn, which supports follow-ups such as "that", "it" or "those". How well references are resolved depends on the model; ambiguous ones are stated as an assumption. |
| Topics can change naturally | One agent with tools for Pokémon, types, moves and abilities; no fixed script. |
| Python, FastAPI and LangGraph | `StateGraph` agent with a tool node and a checkpointer, served by FastAPI. |
| Pokémon information comes from PokeAPI | All factual lookups go through tools that call PokeAPI. The system prompt tells the model to use them and not to answer facts from memory; this is instructed, not mechanically enforced (see limitations). |

**Added beyond the brief:** Pokémon cards (artwork, type badges, stat bars, source link), typo tolerance ("Pikachoo" → Pikachu), exact dual-type weakness maths done in code, username/password login with rate limits, model fallback, and rollback of failed turns.

## Example conversation

Abridged from real runs against `gemini-3.5-flash-lite`. Wording varies between runs because the answers are written by the model.

> **Bot:** Hey there, what’s up?
> **You:** What's a Pikachu?
> **Bot:** Pikachu is an Electric-type Mouse Pokémon from Generation I. It evolves from Pichu (with high enough friendship) and can evolve into Raichu using a Thunder Stone (though evolution methods can vary by game). *(+ Pikachu card)*
> **You:** How's that different from a Charizard?
> **Bot:** Charizard is a Fire and Flying-type Flame Pokémon… base stat total 534 vs Pikachu's 320… *(+ Pikachu and Charizard cards side by side)*
> **You:** What's it weak to?
> **Bot:** Assuming you mean Charizard, it is 4x weak to Rock, and 2x weak to Electric and Water types.
> **You:** What about the other one?
> **Bot:** Assuming you mean Pikachu, it is only weak to Ground-type moves, taking 2x damage from them.
> **You:** Where can I catch Eevee?
> **Bot:** I cannot look up where to catch Pokémon.

## Three-minute evaluation walkthrough

Start a chat (click **New chat**) and ask these in order:

| # | Ask | What to look for |
|---|---|---|
| 1 | *(open a new chat)* | The first bubble is exactly `Hey there, what’s up?` |
| 2 | What's a Pikachu? | A short intro and a Pikachu card (artwork, type badge, stat bars, "Source: PokeAPI" link) |
| 3 | How's that different from a Charizard? | A comparison; two cards side by side. "that" is resolved from the chat. |
| 4 | What's it weak to? | The bot states which Pokémon it assumed. For Charizard: Rock 4×, Water 2×, Electric 2×, immune to Ground. |
| 5 | What does Eevee evolve into, and how? | Eight evolutions with the methods PokeAPI provides, with a note that methods can vary by game |
| 6 | Which of those is fire type? | "those" resolves to Eevee's evolutions (Flareon) |
| 7 | What does the move thunderbolt do? | Power 90, accuracy 100, PP 15, 10% paralysis chance |
| 8 | Tell me about Pikachoo | Auto-corrected to Pikachu, and the bot says so |
| 9 | Tell me about Zzzzzz | A friendly "not found" and a question about what you meant |
| 10 | Can Pikachu learn Thunderbolt in Pokémon Violet? | A plain statement that this is not supported (no learnset data) |
| 11 | Best pizza topping? | A short redirect back to Pokémon |

While a reply is loading, the input box, Send and **New chat** are disabled.

## Supported topics and limitations

| Supported (via PokeAPI tools) | Not supported |
|---|---|
| A Pokémon's types, base stats, abilities, height, weight, category, description, generation, legendary status | Which moves a Pokémon can learn |
| Evolution paths and the evolution conditions PokeAPI lists | Game-specific evolution rules or availability |
| Type matchups, including exact multipliers for two-type Pokémon | Where to catch Pokémon (encounters), items, locations |
| Move details (type, power, accuracy, PP, effect) | Teams, strategy or competitive advice |
| Ability effects and example Pokémon | Anything not about Pokémon (the bot redirects politely) |

When asked for something unsupported, the bot is instructed to say so instead of guessing. Evolution methods and ability effects come from PokeAPI's current data and may not match a specific game version.

## Quick start (from git clone to running)

You need **Python 3.12+** and a **Gemini API key** from [Google AI Studio](https://aistudio.google.com/apikey).

```bash
git clone https://github.com/jahanv01/Pokemon-Chatbot-MVP.git
cd Pokemon-Chatbot-MVP
bash setup.sh
```

`setup.sh` creates the virtual environment, installs the packages, **asks for your Gemini key and a chat username and password** (typed secrets are hidden), writes `.env`, and starts the app. Then open **http://127.0.0.1:8000** and log in with the username and password you chose.

- Works on macOS, Linux and Windows (use **Git Bash**, included with Git for Windows).
- Run it again any time; it keeps your existing `.env` if you answer "Y".
- `bash setup.sh --no-run` sets up without starting the server.
- Start later with `.venv/bin/python -m uvicorn app.main:app` (Windows: `.venv/Scripts/python -m uvicorn app.main:app`).
- `GET /health` returns `{"status":"ok"}` when the **web server** is running. It does not check Gemini or PokeAPI.

<details>
<summary>Manual setup (without the script), and Docker</summary>

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # then edit .env: GOOGLE_API_KEY, APP_ACCESS_USERNAME, APP_ACCESS_PASSWORD
python -m uvicorn app.main:app
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then edit .env: GOOGLE_API_KEY, APP_ACCESS_USERNAME, APP_ACCESS_PASSWORD
python -m uvicorn app.main:app
```

**Docker**

```bash
docker build -t pokemon-chatbot .
docker run --env-file .env -p 8000:8000 pokemon-chatbot
```

Restart the server after editing `.env`.

</details>

## Architecture and design decisions

**The agent loop** (`app/graph.py`)

```
START → agent (LLM) ──tool calls?──► tools (ToolNode) ──► agent … → END
```

- `StateGraph(MessagesState)` with an `agent` node and a `ToolNode(handle_tool_errors=True)`, so a PokeAPI outage becomes a message the bot can explain instead of crashing the request.
- `InMemorySaver` is the checkpointer and `thread_id = session_id`; this is what gives each chat its memory.
- `recursion_limit` (16) stops a confused model from looping forever.
- The greeting is stored with `aupdate_state(..., as_node="agent")`. Leading assistant messages are dropped before calling the model, because some providers reject a conversation that starts with one.
- **Model fallback:** if the main model raises an error (for example a quota error), the next model in `LLM_FALLBACK_MODELS` is tried. This improves resilience but does not guarantee an answer.
- **Failed turns are rolled back:** if a turn fails part-way, the messages it added are removed so a retry starts from a clean history (covered by a regression test).

**Tools** (`app/tools.py`): each returns compact JSON text, not the raw PokeAPI response.

| Tool | Returns |
|---|---|
| `get_pokemon(name)` | Types, stats with total, abilities (hidden flagged), height in m, weight in kg, category, English description, generation, legendary flag, and evolution paths with how each stage is reached. Also produces a card for the UI. |
| `get_type_matchups(type_names)` | For one or two types: exact multipliers for weak-to (4×, 2×), resists (0.5×, 0.25×), immune-to and super-effective-against. Calculated in code so the model does not do the arithmetic. |
| `get_move(name)` | Type, power, accuracy, PP, category, effect and effect chance. |
| `get_ability(name)` | Effect and example Pokémon. |

**PokeAPI client** (`app/pokeapi.py`)

- Async `httpx`. `get_json` returns `None` on 404 and raises `PokeAPIError` on network or 5xx errors.
- In-memory TTL cache keyed by URL; 404s are remembered briefly too.
- `normalize_name` maps user spelling to slugs ("Mr. Mime" → `mr-mime`, "Farfetch'd" → `farfetchd`, "Nidoran♀" → `nidoran-f`).
- Species fallback for forms: `/pokemon/deoxys` 404s, so it uses `/pokemon-species/deoxys` and its default variety.
- Height (decimetres) and weight (hectograms) are divided by 10; descriptions are filtered to English and whitespace-cleaned.
- Evolution chains are flattened recursively (Eevee has 8 branches).

**Typo tolerance:** the full name list is fetched once and cached. `difflib.get_close_matches(cutoff=0.7)` finds candidates. A name is auto-corrected only when the best score is at least 0.8 and leads the runner-up by at least 0.08 ("Pikachoo" scores exactly 0.8). Otherwise the tool returns suggestions and the bot asks "Did you mean…?".

**Cards:** `get_pokemon` uses `response_format="content_and_artifact"`. The model reads the text; the card travels on the tool message's `artifact` and is returned beside the reply.

**Sessions and input blocking** (`app/main.py`): each session has an `asyncio.Lock`; a second message while one is running gets a 409. To return only this turn's cards, the message count is taken before the call and only the new messages are read afterwards.

**Access control** (`app/auth.py`): `POST /api/login` checks the username and password in constant time and returns a random bearer token that every session endpoint requires. Wrong logins are limited per IP and requests per token. With no credentials configured, login is disabled. This is a single shared login, not per-user accounts, and it does not tie a session to a particular user.

## Testing and verification

```bash
pytest
```

The suite needs no API key, password or internet. PokeAPI is mocked with `respx` using small PokeAPI-shaped fixtures, and the LLM is a `BaseChatModel` subclass that returns scripted messages (including tool calls) and records every prompt it receives. It covers: history carried to turn 2, the exact greeting, isolated sessions, 409/404/422/502, tool failures explained instead of crashing, rollback of a failed turn and a successful retry, typo correction and suggestions, `NOT_FOUND`, caching, evolution flattening, dual-type matchups, cards, model fallback, login and rate limits.

**What the tests do not show:** these tests verify application behaviour, not live-model answer quality, Gemini availability or browser usability.

**Manual checks by the author** (live Gemini `gemini-3.5-flash-lite`, free-tier key, one machine): a scripted conversation covering follow-ups, comparisons, ambiguous references, an unsupported question and a distress message. Factual turns called PokeAPI tools, and turns that needed no data called none. Typical turns took roughly 1–4 seconds and used 1–2 model calls (one extra call when a tool is used); occasional turns were much slower. These are observations from a small sample, not guarantees.

## Configuration (`.env`)

Copy `.env.example` to `.env` (the setup script does this for you). Settings are read with pydantic-settings, so any of them can also be real environment variables.

| Variable | Default | Meaning |
|---|---|---|
| `GOOGLE_API_KEY` | – | Gemini API key. |
| `LLM_MODEL` | `google_genai:gemini-3.5-flash-lite` | `provider:model` string for LangChain's `init_chat_model`. |
| `LLM_FALLBACK_MODELS` | `google_genai:gemini-3.5-flash` | Comma-separated backups tried in order when the main model errors. |
| `APP_ACCESS_USERNAME` | – | Login username. If unset, nobody can log in. |
| `APP_ACCESS_PASSWORD` | – | Login password. If unset, nobody can log in. |
| `TOKEN_TTL_SECONDS` | `43200` | How long a login token is valid (12 hours). |
| `POKEAPI_BASE_URL` | `https://pokeapi.co/api/v2` | Override to use a mirror. |
| `CACHE_TTL_SECONDS` | `3600` | How long PokeAPI responses are cached. |
| `NOT_FOUND_TTL_SECONDS` | `60` | How long a 404 is remembered. |
| `RECURSION_LIMIT` | `16` | Max graph steps per message. |

**Quotas:** free-tier Gemini usage is limited per model and the limits change, so see Google's [rate limit documentation](https://ai.google.dev/gemini-api/docs/rate-limits) and your AI Studio usage page. Usage per question varies: a simple question takes one model call, and a question that needs data takes at least two (one to choose a tool, one to write the answer), more if several tools are used. Model names also change; check which models your key can use.

**Another provider:** install its package (for example `pip install langchain-openai`), set its key (for example `OPENAI_API_KEY`) and set `LLM_MODEL=openai:<model-name>`.

## API reference

All `/api/sessions…` calls need the header `Authorization: Bearer <token>`.

| Endpoint | Purpose | Notes |
|---|---|---|
| `POST /api/login` | `{username, password}` → `{token}` | 401 wrong login, 429 too many attempts, 503 credentials not configured |
| `POST /api/sessions` | Create a chat → `{session_id, greeting}` | 503 if the model cannot be set up (for example no API key) |
| `POST /api/sessions/{id}/messages` | `{message}` → `{reply, cards}` | 409 still working, 404 unknown session, 422 empty or over 1,000 characters, 429 too fast, 502 model or PokeAPI failure |
| `GET /api/sessions/{id}/messages` | Chat history | 404 unknown session |
| `GET /health` | Web server is up | Public; does not check Gemini or PokeAPI |

```bash
TOKEN=$(curl -s localhost:8000/api/login -H "Content-Type: application/json" \
  -d '{"username":"YOUR_USER","password":"YOUR_PASS"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
SID=$(curl -s -X POST localhost:8000/api/sessions -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -s localhost:8000/api/sessions/$SID/messages -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"message":"What is a Pikachu?"}'
```

## Privacy and session behaviour

- **Your messages are sent to the model provider** (Gemini) to generate replies. Only Pokémon names and types are sent to PokeAPI as lookups. Check Google's terms for the free tier, which may allow content to be used to improve their products. Don't type personal information.
- **Chats live in server memory.** Restarting the server deletes all conversations and logins.
- **Refreshing the page starts a new chat.** The browser does not restore the previous one; the old session simply stays unused in memory until the server restarts. **New chat** does the same without a refresh.
- **Chat sessions and logins are separate.** A login token lasts `TOKEN_TTL_SECONDS` (12 hours by default) and is kept in the browser tab's session storage. Chat sessions do not expire on their own.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Login says credentials are not configured (503) | `APP_ACCESS_USERNAME` or `APP_ACCESS_PASSWORD` is missing in `.env`. |
| "The chatbot isn't configured yet" (503) when a chat starts | The model could not be set up, usually because `GOOGLE_API_KEY` is missing. Restart after editing `.env`. |
| "Sorry, I couldn't get an answer right now" (502) | An invalid key, a model name your key can't use, a quota limit or an outage fails at the first model request, so you see it here rather than at startup. The real cause is printed in the server terminal. A `429 RESOURCE_EXHAUSTED` means that model's quota is used up: wait, add a fallback model, or use a key with higher limits. A `404 NOT_FOUND … model` means the model name isn't available to your key. |
| Answers are slow | Some models spend time "thinking" and free tiers can be busy. The default is a lighter model. |
| `pip` fails with a path-too-long error on Windows | Clone into a shorter folder (for example `C:\src\pokemon`) or enable Windows long paths. |
| Page loads but markdown looks plain | The UI loads `marked` and `DOMPurify` from a CDN and needs internet access. |

## Known limitations and next steps

- **Facts are grounded by instruction, not enforcement.** The model is told to use tools and not to answer from memory, and the live checks showed it doing so, but a model could still answer without a tool. Next: tool-call tracing, a live evaluation set, and a check that factual answers cite tool results.
- **Answer quality depends on the model.** Reference resolution, brevity and tone can vary between runs and models.
- **Sessions are in memory.** A restart loses everything and it only works with one server process. Next: a persistent checkpointer (SQLite/Postgres) and shared locks and tokens (Redis).
- **Unbounded resource use.** Sessions and cache entries are never expired, and there is no request deadline or shared quota budget. Next: session expiry, bounded storage and timeouts before any public deployment.
- **Simple access control.** One shared login with in-memory tokens and rate limits suits a demo, not many users; sessions are not bound to a user. Next: per-user accounts (for example OAuth), session ownership checks and HTTPS.
- **Full context, no trimming.** The whole history is sent each turn, so very long chats get slower and costlier. Next: summarise or trim old turns.
- **No streaming.** The reply appears all at once after a typing indicator. Next: stream over SSE.
- **Evolution answers are not game-specific.** PokeAPI's conditions are shown without a game version; a game-aware answer needs more data and a clarifying question.
- **Coverage is four lookups** (Pokémon, type, move, ability). Learnsets, encounters, items and locations are not supported.
- **No CI/CD pipeline yet** (for example GitHub Actions running `pytest`).

## Project layout

```
app/
  config.py      settings (pydantic-settings, loads .env)
  pokeapi.py     async PokeAPI client, cache, name normalising, typo suggestions
  tools.py       the four LLM tools and the card builder
  graph.py       LangGraph agent, system prompt, greeting, model fallback
  auth.py        login, tokens, rate limits
  main.py        FastAPI endpoints, failed-turn rollback, chat page route
  static/index.html   single-page chat UI (vanilla JS, marked + DOMPurify)
tests/           pytest suite (mocked PokeAPI, scripted fake LLM)
setup.sh  Dockerfile  requirements.txt  .env.example  pytest.ini
```
