# Pokémon Chatbot MVP

A web chatbot that answers Pokémon questions using live data from [PokeAPI](https://pokeapi.co). It greets you, remembers the whole conversation (so "that", "it" and "those" work), and moves freely from one Pokémon topic to another. It is built with **LangGraph + FastAPI** and uses a Gemini model (free tier works).

```
Browser UI ──► FastAPI (login, sessions, locks) ──► LangGraph agent (LLM ⇄ tools) ──► PokeAPI client (async httpx + cache)
```

## Contents

1. [Quick start](#quick-start-from-git-clone-to-running)
2. [What it does](#what-it-does)
3. [Try these questions](#try-these-questions)
4. [Configuration](#configuration-env)
5. [How it works](#how-it-works)
6. [API reference](#api-reference)
7. [Project layout](#project-layout)
8. [Tests](#tests)
9. [Troubleshooting](#troubleshooting)
10. [Known limitations and next steps](#known-limitations-and-next-steps)

## Quick start (from git clone to running)

You need **Python 3.12+** and a free **Gemini API key** from [Google AI Studio](https://aistudio.google.com/apikey).

```bash
git clone <repo-url>
cd Pokemon-Chatbot-MVP
bash setup.sh
```

`setup.sh` does everything: it creates the virtual environment, installs the packages, **asks you for your Gemini key and a chat username and password** (typed secrets are hidden), writes `.env`, and starts the app. Then open **http://127.0.0.1:8000** and log in with the username and password you just chose.

- Works on macOS, Linux and Windows (run it from **Git Bash**, which comes with Git for Windows).
- Run it again any time: it keeps your existing `.env` if you answer "Y".
- `bash setup.sh --no-run` sets everything up without starting the server.
- Later runs: `.venv/bin/python -m uvicorn app.main:app` (Windows: `.venv/Scripts/python -m uvicorn app.main:app`).
- `http://127.0.0.1:8000/health` returns `{"status":"ok"}` when the server is up.

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

The three values you must set in `.env`:

| Variable | Meaning |
|---|---|
| `GOOGLE_API_KEY` | Your Gemini API key |
| `APP_ACCESS_USERNAME` | Username for the chat login |
| `APP_ACCESS_PASSWORD` | Password for the chat login |

Restart the server after editing `.env`.

</details>

## What it does

**Core requirements**

- **Greeting:** every new chat starts with exactly `Hey there, what’s up?`.
- **A response for every input:** the input box and Send button are disabled while a reply is generated, and the API refuses overlapping messages (409).
- **Full conversation context:** the whole history is sent to the model on every turn, so references like "that", "it" and "those" resolve correctly.
- **Topic flexibility:** the conversation can move freely between Pokémon, types, moves, abilities and evolutions.
- **Facts come from PokeAPI, not LLM memory:** types, stats, abilities, evolution methods, moves and type matchups are fetched through tools.

**Added beyond the brief**

- **Pokémon cards:** artwork, Pokédex number, category, coloured type badges, stat bars and a "Source: PokeAPI" link. Comparing two Pokémon shows two cards side by side.
- **Typo tolerance:** "Pikachoo" is corrected to Pikachu (and the bot says so), while an ambiguous typo gets a "Did you mean…?" question.
- **Exact dual-type matchups:** weaknesses and resistances for two-type Pokémon are calculated in code (Charizard: Rock 4×, Water 2×, Electric 2×, immune to Ground), not by the LLM.
- **Access control:** username and password login, random session tokens and rate limits, so only people you give the login to can spend your API quota.
- **Model fallback:** if the main model errors (for example its free daily quota is used up), the next model in the list answers.
- **Web UI:** chat bubbles, typing indicator, markdown rendering, suggestion chips, "New chat" button, light and dark theme.

## Try these questions

Ask these in order in one chat (click **New chat** first):

| # | Ask | What it shows |
|---|---|---|
| 1 | *(open a new chat)* | The exact greeting |
| 2 | What's a Pikachu? | PokeAPI facts and a Pikachu card |
| 3 | How's that different from a Charizard? | "that" resolved from context; two cards side by side |
| 4 | What's it weak to? | "it" means Charizard; Rock 4×, Water 2×, Electric 2×, Ground immune |
| 5 | What does Eevee evolve into, and how? | All 8 evolutions with the real methods from PokeAPI |
| 6 | Which of those is fire type? | "those" resolved (Flareon) |
| 7 | What does the move thunderbolt do? | Power 90, accuracy 100, PP 15, 10% paralysis chance |
| 8 | Tell me about Pikachoo | Typo auto-corrected to Pikachu, and the bot says so |
| 9 | What does the ability static do? | Ability effect and example Pokémon |
| 10 | Tell me about Zzzzzz | Friendly "not found" and a question about what you meant |
| 11 | Best pizza topping? | A short, polite redirect back to Pokémon |

## Configuration (`.env`)

Copy `.env.example` to `.env`. Settings are read with pydantic-settings, so any of them can also be real environment variables.

| Variable | Default | Meaning |
|---|---|---|
| `GOOGLE_API_KEY` | – | Gemini API key (free tier works). |
| `LLM_MODEL` | `google_genai:gemini-3.5-flash-lite` | `provider:model` string for LangChain's `init_chat_model`. |
| `LLM_FALLBACK_MODELS` | `google_genai:gemini-3.5-flash` | Comma-separated backups tried in order when the main model fails. |
| `APP_ACCESS_USERNAME` | – | Login username. If unset, nobody can log in. |
| `APP_ACCESS_PASSWORD` | – | Login password. If unset, nobody can log in. |
| `TOKEN_TTL_SECONDS` | `43200` | How long a login lasts (12 hours). |
| `POKEAPI_BASE_URL` | `https://pokeapi.co/api/v2` | Point at a mirror if you like. |
| `CACHE_TTL_SECONDS` | `3600` | How long PokeAPI responses are cached. |
| `NOT_FOUND_TTL_SECONDS` | `60` | How long a 404 is remembered. |
| `RECURSION_LIMIT` | `16` | Max graph steps per message, so a confused model cannot loop forever. |

**Free-tier note:** Gemini's free tier allows only a small number of requests per day, **per model** (about 20 for some models). One chat question uses 2–3 requests (one to choose a tool, one to write the answer). The fallback list helps, because each model has its own quota. Model names change over time; to see what your key can use, list models with the `google-genai` client or check AI Studio.

**Another provider:** install its package (for example `pip install langchain-openai`), set its key (for example `OPENAI_API_KEY`) and set `LLM_MODEL=openai:gpt-4o-mini`.

## How it works

**The agent loop** (`app/graph.py`)

```
START → agent (LLM) ──tool calls?──► tools (ToolNode) ──► agent … → END
```

- `StateGraph(MessagesState)` with an `agent` node and a `ToolNode(handle_tool_errors=True)`, so a PokeAPI outage becomes a message the bot can explain instead of a crash.
- `InMemorySaver` is the checkpointer and `thread_id = session_id`, which is what gives the bot conversation memory.
- `recursion_limit` (16) stops runaway tool loops.
- The system prompt tells the model to use tools for every fact, resolve references from history, write for beginners, redirect off-topic questions, and ask what was meant on `NOT_FOUND`.
- The greeting is stored in the history with `aupdate_state(..., as_node="agent")`. Leading assistant messages are dropped before calling the model, because some providers reject a conversation that starts with one.

**Tools** (`app/tools.py`): each returns compact JSON text, never the raw PokeAPI response.

| Tool | Returns |
|---|---|
| `get_pokemon(name)` | Types, stats with total, abilities (hidden flagged), height in m, weight in kg, category, English description, generation, legendary flag, and every evolution path with how each stage is reached. Also returns a card for the UI. |
| `get_type_matchups(type_names)` | For one or two types: exact multipliers for weak-to (4×, 2×), resists (0.5×, 0.25×), immune-to, and super-effective-against. |
| `get_move(name)` | Type, power, accuracy, PP, category, effect and effect chance. |
| `get_ability(name)` | Effect and example Pokémon. |

**PokeAPI client** (`app/pokeapi.py`)

- Async `httpx` client. `get_json` returns `None` on 404 and raises `PokeAPIError` on network or 5xx errors.
- In-memory TTL cache (`url → (expiry, data)`), also used to remember 404s for a short time.
- `normalize_name` turns user spelling into PokeAPI slugs ("Mr. Mime" → `mr-mime`, "Farfetch'd" → `farfetchd`, "Nidoran♀" → `nidoran-f`).
- Species fallback: `/pokemon/deoxys` 404s, so it tries `/pokemon-species/deoxys` and uses the default variety.
- Unit handling: height (decimetres) and weight (hectograms) are divided by 10. Description text is filtered to English and whitespace-cleaned.
- Evolution chains are flattened recursively (Eevee has 8 branches).

**Typo tolerance:** the full name list is fetched once and cached. `difflib.get_close_matches(cutoff=0.7)` finds candidates. A name is auto-corrected only when the best score is at least 0.8 and leads the runner-up by at least 0.08 (so "Pikachoo", which scores exactly 0.8, is corrected). Otherwise the tool returns suggestions and the bot asks "Did you mean…?".

**Cards:** `get_pokemon` uses `response_format="content_and_artifact"`. The LLM reads the text and the card rides along on the tool message's `artifact`; the API returns it next to the reply.

**Sessions and input blocking** (`app/main.py`): each session has an `asyncio.Lock`. A second message while one is running gets a 409. To return this turn's cards, the message count is taken before the call and only the new messages are read afterwards.

**Access control** (`app/auth.py`): `POST /api/login` checks the username and password in constant time and returns a random bearer token. All session endpoints require it. Wrong logins are limited to 5 per 5 minutes per IP, and each token to 30 requests per minute. Without configured credentials, login is disabled (fail closed).

## API reference

All `/api/sessions…` calls need the header `Authorization: Bearer <token>`.

| Endpoint | Purpose | Notes |
|---|---|---|
| `POST /api/login` | `{username, password}` → `{token}` | 401 wrong login, 429 too many attempts, 503 credentials not configured |
| `POST /api/sessions` | Create a chat → `{session_id, greeting}` | 503 if the LLM key is missing |
| `POST /api/sessions/{id}/messages` | `{message}` → `{reply, cards}` | 409 still working, 404 unknown session, 422 empty or over 1,000 characters, 429 too fast, 502 LLM failure |
| `GET /api/sessions/{id}/messages` | Chat history | 404 unknown session |
| `GET /health` | Health check | Public |

Example with curl:

```bash
TOKEN=$(curl -s localhost:8000/api/login -H "Content-Type: application/json" \
  -d '{"username":"YOUR_USER","password":"YOUR_PASS"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
SID=$(curl -s -X POST localhost:8000/api/sessions -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -s localhost:8000/api/sessions/$SID/messages -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"message":"What is a Pikachu?"}'
```

## Project layout

```
app/
  config.py      settings (pydantic-settings, loads .env)
  pokeapi.py     async PokeAPI client, cache, name normalising, typo suggestions
  tools.py       the four LLM tools and the card builder
  graph.py       LangGraph agent, system prompt, greeting, model fallback
  auth.py        login, tokens, rate limits
  main.py        FastAPI endpoints and the chat page route
  static/index.html   single-page chat UI (vanilla JS, marked + DOMPurify)
tests/           pytest suite (mocked PokeAPI, scripted fake LLM)
setup.sh  Dockerfile  requirements.txt  .env.example  pytest.ini
```

## Tests

```bash
pytest
```

The suite runs with no API key, no password and no internet. PokeAPI is mocked with `respx` using small PokeAPI-shaped fixtures, and the LLM is a `BaseChatModel` subclass that returns scripted messages (including tool calls) and records every prompt it receives. It covers: context carried to turn 2, the exact greeting, isolated sessions, 409/404/422/502, tool failures explained instead of crashing, typo correction and suggestions, `NOT_FOUND`, caching, evolution flattening, exact dual-type matchups, cards, model fallback, login and rate limits.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Login says credentials are not configured (503) | `APP_ACCESS_USERNAME` or `APP_ACCESS_PASSWORD` missing in `.env`. |
| "The chatbot isn't configured yet" (503) | `GOOGLE_API_KEY` is missing or wrong in `.env`. Restart after editing. |
| "Sorry, I couldn't get an answer right now" (502) | The real cause is printed in the server terminal. `429 RESOURCE_EXHAUSTED` means that model's free quota is used up, so wait, add a fallback model, or use a paid key. `404 NOT_FOUND … model` means the model name is not available to your key. |
| Answers are slow | Some Gemini models "think" before answering and free tiers can be busy. Prefer a flash-lite model (the default). |
| `pip` fails with a path-too-long error on Windows | Clone into a shorter folder (for example `C:\\src\\pokemon`) or enable Windows long paths. |
| Page loads but styling/markdown looks plain | The UI loads `marked` and `DOMPurify` from a CDN and needs internet access. |

## Known limitations and next steps

- **Sessions are in memory.** A restart loses all chats and logins, and it only works with a single server process. Next: a persistent checkpointer (SQLite or Postgres) and shared locks and tokens (for example Redis).
- **Full context, no trimming.** The whole history is sent every turn, so very long chats get slower and costlier. Next: summarise or trim old turns.
- **No streaming yet.** The reply appears all at once after a typing indicator. Next: stream tokens over SSE.
- **Free-tier quotas are small.** A review session can use up a model's daily free requests; the fallback model and a paid key are the remedies.
- **Simple access control.** One shared username and password with in-memory tokens and rate limits suits a demo, not many users. Sessions never expire. Next: per-user accounts (for example OAuth) and HTTPS in front of the app.
- **Answer quality depends on the LLM** following the system prompt. PokeAPI outages are explained to the user but not retried.
- **Coverage:** four lookups only (Pokémon, type, move, ability). Items, locations, encounters and games are not covered.
- **No CI/CD pipeline yet** (for example GitHub Actions running `pytest`).
