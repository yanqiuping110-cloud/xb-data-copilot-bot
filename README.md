# Data Copilot

### Enterprise Natural-Language Analytics

<p align="center">
  <img src="https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square" alt="License"/>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Vue-3-42b883?style=flat-square&logo=vuedotjs&logoColor=white" alt="Vue"/>
  <img src="https://img.shields.io/badge/FastAPI-Async-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/LangGraph-Multi--Agent-1C3C3C?style=flat-square" alt="LangGraph"/>
  <img src="https://img.shields.io/badge/Security-SQL%20Guard%20%7C%20DataScope-b71c1c?style=flat-square" alt="Security"/>
</p>

<p align="center">
  <strong>Ask your enterprise data in natural language</strong> — turn week-long report cycles into minutes.<br/>
  NL2SQL for mid/large business systems: metadata governance, hybrid retrieval, multi-stage reasoning,<br/>
  a fail-closed SQL gateway, and config-driven row-level DataScope — in one product.
</p>

<p align="center">
  <a href="README.zh-CN.md">中文</a> ·
  <a href="AGENTS.md">For AI Agents</a> ·
  <a href="docs/DEMO.md">Demo</a> ·
  <a href="#why-data-copilot">Why</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#docs">Docs</a>
</p>

> **Open Source Demo (Scheme A)** — `make demo-up && make demo-smoke` · UI http://localhost:8080 · `admin` / `demo123456` · **no API key** (Fixture mode). Details: [AGENTS.md](AGENTS.md) · [docs/DEMO.md](docs/DEMO.md)

---

## Why Data Copilot

| | Typical Chat-to-SQL | Data Copilot |
|--|---------------------|--------------|
| Security | Trust the model | **Fail-closed** SQL Guard + DataScope (never rely on the model “behaving”) |
| Permissions | App-layer filters (easy to miss) | Config-driven **row-level grants** injected / checked at execution |
| Knowledge | Schema dump only | **Meta + metrics + optional code graph** hybrid recall |
| Ops | Black box | SSE timeline, spans, audit, badcase → L1 loop |
| Databases | One engine | Catalog-driven **multi-engine** (MySQL / PG / CH / Excel / …) |

**Ask once → secure SQL → table + chart + plain-language answer.**

<p align="center">
  <img src="docs/images/ask-result.png" alt="Ask result: answer, SQL, chart, table" width="920"/>
</p>
<p align="center"><em>Ask workspace · natural-language answer + SQL (ADMIN) + chart / table</em></p>

<p align="center">
  <img src="docs/images/ask-pipeline.png" alt="Ask pipeline timeline" width="920"/>
</p>
<p align="center"><em>Live pipeline · per-node progress & latency</em></p>

---

## Features

- **LangGraph ask pipeline** — memory → hybrid recall → L1 examples → plan / agent tool loop → validate → execute → verify
- **SQL Guard** — SELECT-only AST checks, table allow-list, column deny, LIMIT, DataScope injection
- **DataScope** — RBAC + dimension grants; missing grants fail closed (`NO_DATA_SCOPE`)
- **Prompt hardening** — untrusted boundaries + recall sanitization; execution layer still enforces policy
- **Multi-engine catalogs** — LLM providers & datasources configured in admin UI (YAML catalogs, encrypted secrets)
- **Retrieval** — Zvec by default (vector + FTS + RRF); optional Elasticsearch
- **Observability** — turn / span / audit tables; thumbs feedback → badcase → L1

Admin UI for LLM providers and datasources:

<p align="center">
  <img src="docs/images/admin-llm-providers.png" alt="LLM provider wizard" width="920"/>
</p>
<p align="center">
  <img src="docs/images/admin-datasource-wizard.png" alt="Datasource wizard" width="920"/>
</p>

---

## Architecture

```mermaid
flowchart TB
    subgraph Client
        UI["Vue3 Ask Console"]
        Admin["Meta / Semantics / System Config"]
    end

    subgraph API["FastAPI"]
        Auth["JWT · RBAC"]
        Ask["/ask"]
        Meta["/admin/meta"]
        Sys["/admin/system"]
        Scope["DataScope APIs"]
    end

    subgraph Agent["LangGraph"]
        Recall["Hybrid recall"]
        Plan["Plan · Agent loop"]
        SQLGen["SQL gen · validate · correct"]
        Exec["Execute · verify"]
    end

    subgraph Security
        PB["Prompt boundary"]
        Guard["SQL Guard · DataScope"]
    end

    subgraph Knowledge
        CopilotDB[("copilot DB · meta · audit")]
        Zvec["Zvec / optional ES"]
        CodeKG["Git code graph"]
    end

    subgraph Data
        BizDB[("Business DB · multi-engine RO")]
        LLM["LLM / Embedding"]
    end

    UI --> Auth --> Ask --> Agent
    Admin --> Meta
    Admin --> Sys
    Admin --> Scope
    Agent --> Recall --> Zvec
    Recall --> CopilotDB
    Recall --> CodeKG
    Agent --> PB --> LLM
    SQLGen --> Guard --> BizDB
    Exec --> BizDB
```

**Design:** governance DB (`copilot`) is separate from business DBs. Ask paths are **read-only** against business data. LLM & datasource credentials are encrypted at rest.

---

## Quick Start

### Demo (recommended — no host MySQL / no API key)

```bash
make demo-up && make demo-smoke
# Windows PowerShell:
#   .\scripts\demo_up.ps1
#   .\scripts\demo_smoke.ps1
```

| | |
|--|--|
| UI | http://localhost:8080 |
| API | http://localhost:8000 |
| Login | `admin` / `demo123456` |

Preset Fixture questions are listed in [`demo/profiles/_shared/questions.json`](demo/profiles/_shared/questions.json). Coding agents should start from [`AGENTS.md`](AGENTS.md).

### Local development

| Component | Notes |
|-----------|--------|
| MySQL 5.7+ | Business (RO) + `copilot` governance DB |
| Python 3.10+ | Backend |
| Node.js 18+ | Frontend |
| Zvec (default) | Hybrid recall |
| OpenAI-compatible LLM | Ollama / cloud |

```bash
# Backend
cd backend
cp .env.example .env.development   # or copy on Windows
export APP_ENV=development         # PowerShell: $env:APP_ENV="development"
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# Apply scripts/sql/copilot/V*.sql, then:
python scripts/seed_admin.py
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
cp .env.example .env.development
npm install && npm run dev
# http://127.0.0.1:5173
```

```bash
cd backend && pytest tests/ -q
```

More detail (Chinese): [README.zh-CN.md](README.zh-CN.md) · [docs/DEMO.md](docs/DEMO.md)

---

## Tech stack

| Layer | Choice |
|-------|--------|
| API | Python · FastAPI · SQLAlchemy 2 async |
| Orchestration | LangGraph · LangChain |
| UI | Vue 3 · Vite · Pinia |
| Governance DB | MySQL (demo Compose uses MySQL 8) |
| Retrieval | Zvec (default) · Elasticsearch (optional) |
| Security | JWT · sqlglot · DataScope · prompt boundary |

---

## Docs

| Doc | Topic |
|-----|--------|
| [docs/README.md](docs/README.md) | Doc index (numbered plans) |
| [docs/20-OPENSOURCE_GROWTH_PLAN.md](docs/20-OPENSOURCE_GROWTH_PLAN.md) | Opensource / star-growth plan |
| [docs/02-PROGRESS.md](docs/02-PROGRESS.md) | Implementation progress |
| [docs/01-MVP_DEVELOPMENT_PLAN.md](docs/01-MVP_DEVELOPMENT_PLAN.md) | Full MVP design (CN) |
| [docs/91-PROMPT_SECURITY.md](docs/91-PROMPT_SECURITY.md) | Prompt injection threat model |
| [docs/92-EVAL_QUESTIONS.md](docs/92-EVAL_QUESTIONS.md) | Eval suites (incl. `inj-*`) |
| [AGENTS.md](AGENTS.md) | One-command demo for coding agents |

---

## License

[Apache License 2.0](LICENSE). Replace `JWT_SECRET`, demo passwords, and other secrets before any real deployment. Enable DataScope in production only after migrations and user grants are configured.
