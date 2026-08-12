# Agent Quickstart

Clone this repo and run the demo with **no cloud API key** and **no host MySQL**.

## One command

```bash
# Linux / macOS / Git Bash
make demo-up && make demo-smoke

# Windows PowerShell
.\scripts\demo_up.ps1
.\scripts\demo_smoke.ps1
```

## Defaults

| Item | Value |
|------|--------|
| Governance DB | MySQL 8 **inside Compose** (`MYSQL_COPILOT_HOST=mysql`) |
| Business sample | Excel/ShopPulse profile (`demo/profiles/excel`) |
| LLM | `LLM_MODE=fixture` (no API key) |
| API | http://localhost:8000 |
| UI | http://localhost:8080 |
| Login | `admin` / `demo123456` |

## Success criteria

- `make demo-smoke` (or `demo_smoke.ps1`) exits **0**
- Logs / console contain **`DEMO_READY`**
- Smoke asks a preset question and gets `status=ok` with rows

## Do not

- Do **not** point `MYSQL_COPILOT_*` at a production / company database
- Do **not** require Ollama or a cloud LLM for smoke (Fixture is enough)
- Do **not** edit `youplus-base` / `sport-plantform` if present (reference only)
- Do **not** invent alternate compose files for the first run — use `deploy/docker-compose.demo.yml`

## Troubleshoot

| Symptom | Fix |
|---------|-----|
| Port 8000/3306/8080 busy | `make demo-down` or change ports in compose |
| MySQL not ready | Re-run `make demo-up` (bootstrap waits / retries) |
| Smoke fail | Read `.demo/last-smoke.log` |
| Reset everything | `make demo-reset` then `make demo-up` |

## Bring your own LLM (optional)

After demo is up, set in `backend/.env.demo` (or overlay):

```env
LLM_MODE=openai
LLM_API_BASE=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

Restart API container. Open-domain questions then use the real model; Fixture presets still work if you keep `LLM_MODE=fixture`.

## Docs

- Human guide: [docs/DEMO.md](docs/DEMO.md)
- Full opensource plan: [docs/20-OPENSOURCE_GROWTH_PLAN.md](docs/20-OPENSOURCE_GROWTH_PLAN.md)
