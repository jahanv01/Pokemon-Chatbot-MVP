#!/usr/bin/env bash
# One-step setup: creates the venv, installs packages, writes .env (asking for your keys) and starts the app.
# Usage: bash setup.sh            (set up and run)
#        bash setup.sh --no-run   (set up only)
set -euo pipefail  # stop on any error, unset variable or failed pipe

cd "$(dirname "$0")"  # always work from the project folder, wherever the script is called from

# ---- 1. find a working Python 3.12+ ----
PY=""  # will hold the python command we use
for cmd in python3 python py; do  # try the common names (py = Windows launcher)
  if "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1; then  # works and is new enough?
    PY="$cmd"  # remember it
    break  # stop looking
  fi
done
if [ -z "$PY" ]; then  # nothing suitable found
  echo "Python 3.12 or newer is required. Install it from https://www.python.org/downloads/ and run this again." >&2
  exit 1
fi

# ---- 2. virtual environment + dependencies ----
if [ ! -d .venv ]; then  # only create it the first time
  echo "Creating virtual environment..."
  "$PY" -m venv .venv  # new isolated environment in ./.venv
fi
if [ -x .venv/Scripts/python ] || [ -f .venv/Scripts/python.exe ]; then  # Windows layout (Git Bash)
  VENV_PY=".venv/Scripts/python"
else  # macOS / Linux layout
  VENV_PY=".venv/bin/python"
fi
echo "Installing packages (this can take a minute)..."
"$VENV_PY" -m pip install -q -r requirements.txt  # install everything the app needs

# ---- 3. .env (ask for the three values) ----
WRITE_ENV="yes"  # assume we need to create it
if [ -f .env ]; then  # never overwrite an existing config silently
  read -r -p ".env already exists. Keep it? [Y/n] " keep  # ask the user
  case "$keep" in [nN]*) WRITE_ENV="yes" ;; *) WRITE_ENV="no" ;; esac  # only rewrite if they say no
fi

if [ "$WRITE_ENV" = "yes" ]; then
  echo "Get a free Gemini key at https://aistudio.google.com/apikey"
  GOOGLE_API_KEY=""  # start empty so the loop below asks
  while [ -z "$GOOGLE_API_KEY" ]; do  # keep asking until something is entered
    read -r -s -p "Gemini API key (hidden): " GOOGLE_API_KEY; echo  # -s hides what is typed
  done
  APP_ACCESS_USERNAME=""
  while [ -z "$APP_ACCESS_USERNAME" ]; do  # username for the chat login
    read -r -p "Choose a chat username: " APP_ACCESS_USERNAME
  done
  APP_ACCESS_PASSWORD=""
  while [ -z "$APP_ACCESS_PASSWORD" ]; do  # password for the chat login
    read -r -s -p "Choose a chat password (hidden): " APP_ACCESS_PASSWORD; echo
  done
  export GOOGLE_API_KEY APP_ACCESS_USERNAME APP_ACCESS_PASSWORD  # hand the values to Python safely (no shell quoting issues)
  "$VENV_PY" scripts/make_env.py  # builds .env from .env.example, quoting special characters safely (tested in tests/test_env_roundtrip.py)
  echo ".env written."
fi

# ---- 4. run ----
if [ "${1:-}" = "--no-run" ]; then  # setup only
  echo "Setup done. Start the app with:  $VENV_PY -m uvicorn app.main:app"
  exit 0
fi
echo "Starting the app at http://127.0.0.1:8000  (press Ctrl+C to stop)"
exec "$VENV_PY" -m uvicorn app.main:app  # run the server in this terminal
