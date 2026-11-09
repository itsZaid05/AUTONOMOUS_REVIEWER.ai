#!/usr/bin/env bash
# Local Docker Desktop/WSL2 bootstrap. Credentials are never printed.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
command -v python3 >/dev/null || { echo 'Install Python 3 with venv in WSL first.' >&2; exit 1; }
command -v docker >/dev/null || { echo 'Enable Docker Desktop integration for this WSL distribution first.' >&2; exit 1; }
docker compose version >/dev/null
docker info >/dev/null
python3 -m venv .verify-venv
.verify-venv/bin/python -m pip install -r requirements-verify.txt
.verify-venv/bin/python scripts/init_env.py
docker compose up -d --build --wait
.verify-venv/bin/python scripts/retain_lncs_template.py
cat <<'MESSAGE'
Local services started:
  Dashboard: http://localhost:8501
  Backend:   http://localhost:8000/docs
  n8n:       http://localhost:5678
  Mailpit:   http://localhost:8025

Before a real-paper run:
1. Edit .env privately: set AI_PROVIDER=gemini, AI_MODEL, AI_API_KEY.
2. Create/sign into the local n8n owner account; set N8N_OWNER_EMAIL and N8N_OWNER_PASSWORD privately in .env.
3. Apply changed configuration: docker compose up -d --force-recreate api worker dashboard
4. Verify a real Gemini request in Dashboard > Setup and connectivity.
5. Follow DEMO_RECORDING.md to configure the conference and supply five actual manuscripts.
Do not share or record .env. Startup alone does not establish real-paper acceptance.
MESSAGE
