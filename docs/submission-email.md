To: tapan@vyoma.work
Subject: Pokémon Chatbot MVP submission (LangGraph + FastAPI + PokeAPI)

Hi Tapan,

Please find my submission for the Pokémon chatbot assignment.

Repo: https://github.com/jahanv01/Pokemon-Chatbot-MVP

How to run
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and add a Gemini API key (free tier) and an access username and password
3. `uvicorn app.main:app`, then open http://127.0.0.1:8000 and log in with that username and password
(Or with Docker: `docker build -t pokemon-chatbot .` then `docker run --env-file .env -p 8000:8000 pokemon-chatbot`.)
Tests need no key: `pytest`.

What it covers
- Exact greeting "Hey there, what’s up?" at the start of every chat
- LangGraph agent (StateGraph + ToolNode + checkpointer) with conversation memory, so implicit references like "that" work
- All facts come from PokeAPI through four tools (Pokémon, type matchups, move, ability)
- Input blocking: UI disables input and the API returns 409 while a reply is generating

What I added beyond the brief
- Pokémon cards (artwork, type badges, stat bars, source link; two side by side for comparisons)
- Typo tolerance with auto-correction and "Did you mean…?" suggestions, plus short 404 caching
- Tests with a mocked PokeAPI and a scripted fake LLM

Limitations
- Sessions are in memory (lost on restart, single process)
- Full conversation context is sent each turn, with no trimming
- No streaming yet
- Access control is one shared username/password with in-memory tokens (no per-user accounts); sessions never expire

Thanks for reviewing. Happy to walk through it.

Best,
<YOUR NAME>
