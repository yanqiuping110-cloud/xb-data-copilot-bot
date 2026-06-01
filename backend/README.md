# 问数后端（FastAPI）

Python API 入口：`app/main.py`。环境变量、**虚拟环境**均在本目录：

| 路径 | 说明 |
|------|------|
| `backend/.venv/` | Python 虚拟环境（`gitignore`） |
| `backend/.env.development` | 本机配置（`gitignore`） |
| `backend/.env.example` | 配置模板 |

```powershell
# 在 backend/ 目录执行
copy .env.example .env.development
$env:APP_ENV = "development"
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

测试：`pytest tests/ -q`（需已 `activate` 且 `APP_ENV=development`）。

详见仓库根目录 [README.md](../README.md)、[docs/DEVELOPMENT_PLAN.md](../docs/DEVELOPMENT_PLAN.md)（**§5.1 中文注释规范**）、[docs/PROGRESS.md](../docs/PROGRESS.md)。
