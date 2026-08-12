# Opensource Demo (Scheme A)

> Governance DB: **MySQL 8 in Docker Compose**. Business sample: **ShopPulse Excel**. LLM: **Fixture** (no API key).  
> AI Agents: start at [AGENTS.md](../AGENTS.md).

## Quick start

```bash
# Linux / macOS
make demo-up && make demo-smoke

# Windows PowerShell
.\scripts\demo_up.ps1
.\scripts\demo_smoke.ps1
```

- UI: http://localhost:8080  
- API: http://localhost:8000  
- Login: `admin` / `demo123456`

Preset questions (Fixture):

- How many orders are there?
- What is the total order amount?
- Which city has the most users?
- Show order counts by status  
（中文同义句见 `demo/profiles/_shared/questions.json`）

## What gets started

| Service | Port | Role |
|---------|------|------|
| `mysql` | 3307→3306 | Governance DB `copilot` |
| `api` | 8000 | FastAPI + auto bootstrap |
| `web` | 8080 | Vue build via nginx (`/api` proxy) |

## Company / legacy

Production can keep **MySQL 5.7** on the host (`MYSQL_COPILOT_*` as today). Demo does **not** require host MySQL.

Migrating the governance DB to PostgreSQL is a **later** option (plan scheme B), not required for opensource first release.

## Optional real LLM

Edit `backend/.env.demo`:

```env
LLM_MODE=openai
LLM_API_BASE=...
LLM_API_KEY=...
LLM_MODEL=...
```

Then `docker compose -f deploy/docker-compose.demo.yml up -d api --force-recreate`.

## Reset

```bash
make demo-reset   # or: .\scripts\demo_down.ps1 -Reset
```

## Layout

```text
deploy/docker-compose.demo.yml
backend/.env.demo
backend/scripts/bootstrap_demo.py
backend/scripts/demo_entrypoint.py
demo/profiles/excel/
AGENTS.md
Makefile
scripts/demo_*.ps1
```
