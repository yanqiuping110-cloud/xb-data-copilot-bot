/**
 * ECharts SSR 渲染核心（与前端 chartAdapter 同源 option）
 */
const echarts = require('echarts')
const { buildEchartsOption } = require('./chartAdapter')

let sharp = null
try {
  sharp = require('sharp')
} catch {
  sharp = null
}

function renderChart(body) {
  const option = buildEchartsOption({
    chartSpec: body.chartSpec || body.chart_spec,
    columns: body.columns || [],
    rows: body.rows || [],
  })
  if (!option) return null

  const width = body.width || 720
  const height = body.height || 400
  const wantPng = (body.format || 'png') !== 'svg'

  const chart = echarts.init(null, null, {
    renderer: 'svg',
    ssr: true,
    width,
    height,
  })
  chart.setOption(option, true)
  const svg = chart.renderToSVGString()
  chart.dispose()

  const result = { width, height, format: 'svg', svgBase64: Buffer.from(svg, 'utf8').toString('base64') }

  if (wantPng && sharp) {
    const png = sharp(Buffer.from(svg)).png()
    return png.toBuffer().then((pngBuf) => ({
      width,
      height,
      format: 'png',
      pngBase64: pngBuf.toString('base64'),
    }))
  }

  return Promise.resolve(result)
}

module.exports = { renderChart }
