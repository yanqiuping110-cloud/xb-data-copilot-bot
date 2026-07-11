/**
 * Chart SSR 侧车服务 · ChartSpec → PNG
 * 企业部署：docker compose 中与 API 同网段运行
 */
const http = require('http')

const PORT = parseInt(process.env.CHART_SSR_PORT || '3001', 10)
const API_KEY = process.env.CHART_SSR_API_KEY || ''

function escapeXml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function chartToSvg(body) {
  const spec = body.chartSpec || body.chart_spec || {}
  const columns = body.columns || []
  const rows = (body.rows || []).slice(0, 30)
  const width = body.width || 720
  const height = body.height || 400
  const title = body.title || spec.title || '图表'
  const chartType = spec.chartType || spec.chart_type || 'bar'

  const colIdx = Object.fromEntries(columns.map((c, i) => [c, i]))
  let xCol = spec.xColumn || spec.x_column || columns[0]
  if (!(xCol in colIdx)) xCol = columns[0]
  let yCols = spec.yColumns || spec.y_columns || []
  if (!yCols.length) yCols = columns.filter((c) => c !== xCol).slice(0, 1)
  yCols = yCols.filter((c) => c in colIdx)
  if (!yCols.length || !rows.length) return null

  const xi = colIdx[xCol]
  const xVals = rows.map((r) => String(r[xi] ?? ''))
  const yi = colIdx[yCols[0]]
  const yVals = rows.map((r) => {
    const v = parseFloat(r[yi])
    return Number.isFinite(v) ? v : 0
  })
  const maxY = Math.max(...yVals, 1)
  const pad = { l: 56, r: 24, t: 48, b: 64 }
  const plotW = width - pad.l - pad.r
  const plotH = height - pad.t - pad.b
  const barW = plotW / Math.max(yVals.length, 1)

  let shapes = ''
  if (chartType === 'line' || chartType === 'area' || chartType === 'trend') {
    const pts = yVals
      .map((v, i) => {
        const x = pad.l + (i + 0.5) * barW
        const y = pad.t + plotH - (v / maxY) * plotH
        return `${x},${y}`
      })
      .join(' ')
    shapes += `<polyline fill="none" stroke="#6366f1" stroke-width="2.5" points="${pts}"/>`
    yVals.forEach((v, i) => {
      const x = pad.l + (i + 0.5) * barW
      const y = pad.t + plotH - (v / maxY) * plotH
      shapes += `<circle cx="${x}" cy="${y}" r="4" fill="#6366f1"/>`
    })
  } else {
    yVals.forEach((v, i) => {
      const bh = (v / maxY) * plotH
      const x = pad.l + i * barW + barW * 0.15
      const y = pad.t + plotH - bh
      shapes += `<rect x="${x}" y="${y}" width="${barW * 0.7}" height="${bh}" fill="#6366f1" rx="3"/>`
    })
  }

  const xLabels = xVals
    .map((lab, i) => {
      const x = pad.l + (i + 0.5) * barW
      const y = height - pad.b + 18
      return `<text x="${x}" y="${y}" font-size="11" fill="#64748b" text-anchor="middle" transform="rotate(25 ${x} ${y})">${escapeXml(lab.slice(0, 12))}</text>`
    })
    .join('')

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="${pad.l}" y="28" font-size="16" font-weight="600" fill="#0f172a">${escapeXml(title)}</text>
  <line x1="${pad.l}" y1="${pad.t + plotH}" x2="${width - pad.r}" y2="${pad.t + plotH}" stroke="#e2e8f0"/>
  ${shapes}
  ${xLabels}
</svg>`
}

/** 简易 SVG rasterize：返回 SVG base64（客户端/Pillow 可转 PNG；此处直接 PNG 需 sharp，暂返 SVG 供 Python 降级） */
function svgToPngBase64(svg) {
  // 无 native 依赖：返回 SVG data URI 的 base64，Python 端识别并转 PNG 或直接用 SVG
  return Buffer.from(svg, 'utf8').toString('base64')
}

const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ ok: true }))
    return
  }
  if (req.method !== 'POST' || req.url !== '/render') {
    res.writeHead(404)
    res.end()
    return
  }
  if (API_KEY) {
    const key = req.headers['x-chart-ssr-key']
    if (key !== API_KEY) {
      res.writeHead(401)
      res.end(JSON.stringify({ error: 'unauthorized' }))
      return
    }
  }
  let raw = ''
  req.on('data', (c) => { raw += c })
  req.on('end', () => {
    try {
      const body = JSON.parse(raw || '{}')
      const svg = chartToSvg(body)
      if (!svg) {
        res.writeHead(422, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ error: 'cannot_render' }))
        return
      }
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(
        JSON.stringify({
          svgBase64: svgToPngBase64(svg),
          format: 'svg',
          width: body.width || 720,
          height: body.height || 400,
        }),
      )
    } catch (e) {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ error: String(e.message || e) }))
    }
  })
})

server.listen(PORT, () => {
  console.log(`chart-ssr listening on :${PORT}`)
})
