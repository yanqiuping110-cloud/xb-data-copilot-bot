# 问数前端（Vue3 + Vite）

```powershell
cd frontend
copy .env.example .env.development
npm install
npm run dev
```

开发期默认 <http://127.0.0.1:5173>；`/api` 由 Vite 代理到 `VITE_API_BASE`（默认 `http://127.0.0.1:8000`）。

需先启动 [backend](../backend/) API。

**注释**：业务逻辑须写中文注释，规范见 [01-MVP_DEVELOPMENT_PLAN.md §5.1](../docs/01-MVP_DEVELOPMENT_PLAN.md)。
