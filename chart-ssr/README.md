# Chart SSR 侧车

ChartSpec → PNG/SVG 的统一服务端渲染，供 Ask 与 Insight PDF 共用。

## 启动

```bash
cd chart-ssr
npm install
node server.js
```

默认监听 `:3001`。使用 **ECharts 5 SSR** 渲染，与前端 `chartAdapter.js` 同款 option（柱状/折线/饼图等）。

**无需常驻侧车时**：Python 会自动调用 `node render-cli.js` 单次渲染（PDF 导出默认走此路径）。

环境变量：

| 变量 | 说明 |
|------|------|
| `CHART_SSR_PORT` | 端口，默认 3001 |
| `CHART_SSR_API_KEY` | 可选，设置后请求需 `X-Chart-Ssr-Key` |

## API

`POST /render`

```json
{
  "chartSpec": { "chartType": "bar", "xColumn": "A", "yColumns": ["B"] },
  "columns": ["A", "B"],
  "rows": [["x", 10], ["y", 20]],
  "width": 720,
  "height": 400,
  "format": "png"
}
```

响应：`{ "svgBase64": "..." }` 或 `{ "pngBase64": "..." }`（Python 端会尝试 cairosvg 转 PNG，失败则降级 matplotlib）。

`GET /health` → `{ "ok": true }`

## 后端配置

```bash
CHART_SSR_ENABLED=true
CHART_SSR_URL=http://127.0.0.1:3001
```

详见 [docs/03-PHASE2_ROADMAP.md](../docs/03-PHASE2_ROADMAP.md) §P2-A。
