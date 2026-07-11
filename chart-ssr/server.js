/**
 * Chart SSR 侧车 · ECharts 与前端页面同款样式
 */
const http = require('http')
const { renderChart } = require('./renderCore')

const PORT = parseInt(process.env.CHART_SSR_PORT || '3001', 10)
const API_KEY = process.env.CHART_SSR_API_KEY || ''

const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ ok: true, engine: 'echarts' }))
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
  req.on('end', async () => {
    try {
      const body = JSON.parse(raw || '{}')
      const result = await renderChart(body)
      if (!result) {
        res.writeHead(422, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ error: 'cannot_render' }))
        return
      }
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify(result))
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ error: String(e.message || e) }))
    }
  })
})

server.listen(PORT, () => {
  console.log(`chart-ssr (echarts) listening on :${PORT}`)
})
