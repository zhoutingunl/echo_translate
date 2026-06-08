#!/usr/bin/env bash
# Convenience launcher: sets up a venv, installs deps, checks .env, runs the app.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "→ creating virtualenv (.venv)"
  python3.11 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "⚠️  created .env from template — edit it and set MINIMAX_API_KEY, then re-run."
  exit 1
fi

exec python app.py
