/**
 * 将 columns/rows + chartSpec 转为 ECharts option。
 */

const CHART_COLORS = ['#6366f1', '#22c55e', '#06b6d4', '#f59e0b', '#8b5cf6', '#ec4899']
const CHART_BACKGROUND = 'transparent'

function pickSpec(spec, ...keys) {
  for (const k of keys) {
    if (spec[k] != null && spec[k] !== '') return spec[k]
  }
  return undefined
}

function rowObjects(columns, rows) {
  if (!columns?.length || !rows?.length) return []
  return rows.map((row) =>
    Object.fromEntries(columns.map((col, i) => [col, row[i]])),
  )
}

function numericVal(v) {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function applyLimit(records, xColumn, yColumns, limit) {
  if (!limit || records.length <= limit) return records
  const yCol = yColumns[0]
  return [...records]
    .sort((a, b) => (numericVal(b[yCol]) ?? 0) - (numericVal(a[yCol]) ?? 0))
    .slice(0, limit)
}

function axisLabelRotate(categories) {
  if (categories.length <= 4) return 0
  if (categories.length <= 6) return categories.some((c) => c.length > 6) ? 20 : 0
  return 35
}

/**
 * @param {{ chartSpec?: object, columns?: string[], rows?: array[] }} params
 * @returns {object|null}
 */
export function buildEchartsOption({ chartSpec, columns, rows }) {
  if (!chartSpec || chartSpec.status !== 'ready') return null
  const spec = chartSpec
  const records = rowObjects(columns, rows)
  if (!records.length) return null

  const xCol = pickSpec(spec, 'xColumn', 'x_column')
  const yCols = pickSpec(spec, 'yColumns', 'y_columns') || []
  const limit = spec.options?.limit
  const data = xCol ? applyLimit(records, xCol, yCols, limit) : records

  const chartType = pickSpec(spec, 'chartType', 'chart_type')
  const baseTooltip = {
    trigger: 'item',
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderColor: '#e2e8f0',
    borderWidth: 1,
    textStyle: { color: '#334155', fontSize: 12 },
  }

  if (chartType === 'pie') {
    const yCol = yCols[0]
    if (!xCol || !yCol) return null
    return {
      backgroundColor: CHART_BACKGROUND,
      color: CHART_COLORS,
      tooltip: baseTooltip,
      legend: { bottom: 0, type: 'scroll', textStyle: { color: '#64748b' } },
      series: [
        {
          type: 'pie',
          radius: ['38%', '64%'],
          itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
          label: { color: '#475569' },
          data: data.map((r) => ({
            name: String(r[xCol] ?? ''),
            value: numericVal(r[yCol]) ?? 0,
          })),
        },
      ],
    }
  }

  if (chartType === 'scatter') {
    const x = yCols[0]
    const y = yCols[1]
    if (!x || !y) return null
    return {
      backgroundColor: CHART_BACKGROUND,
      color: CHART_COLORS,
      tooltip: baseTooltip,
      grid: { left: 52, right: 24, top: 24, bottom: 48 },
      xAxis: { type: 'value', name: x, axisLine: { lineStyle: { color: '#e2e8f0' } } },
      yAxis: { type: 'value', name: y, splitLine: { lineStyle: { color: '#f1f5f9' } } },
      series: [
        {
          type: 'scatter',
          symbolSize: 10,
          data: data.map((r) => [numericVal(r[x]), numericVal(r[y])]),
        },
      ],
    }
  }

  const categories = xCol ? data.map((r) => String(r[xCol] ?? '')) : data.map((_, i) => String(i + 1))
  const isLine = chartType === 'line' || chartType === 'area'
  const labelRotate = axisLabelRotate(categories)
  const seriesList = (spec.series?.length ? spec.series : yCols.map((c) => ({ name: c, column: c }))).map(
    (s, idx) => {
      const col = s.column || yCols[idx]
      let type = s.type || (isLine ? 'line' : 'bar')
      if (chartType === 'combo') {
        type = s.type || (idx === 0 ? 'bar' : 'line')
      } else if (isLine) {
        type = 'line'
      } else {
        type = 'bar'
      }
      const base = {
        name: s.name || col,
        type,
        smooth: type === 'line',
        data: data.map((r) => numericVal(r[col])),
      }
      if (type === 'bar') {
        base.barMaxWidth = 42
        base.itemStyle = { borderRadius: [4, 4, 0, 0] }
      }
      if (type === 'line') {
        base.symbolSize = 7
        base.lineStyle = { width: 2.5 }
        if (chartType === 'area') base.areaStyle = { opacity: 0.12 }
      }
      return base
    },
  )

  return {
    backgroundColor: CHART_BACKGROUND,
    color: CHART_COLORS,
    tooltip: { ...baseTooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: yCols.length > 1
      ? { top: 0, right: 0, textStyle: { color: '#64748b', fontSize: 12 } }
      : undefined,
    grid: {
      left: 52,
      right: 24,
      top: yCols.length > 1 ? 40 : 28,
      bottom: labelRotate > 0 ? 64 : 48,
    },
    xAxis: {
      type: 'category',
      data: categories,
      boundaryGap: !isLine,
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisTick: { show: false },
      axisLabel: {
        color: '#64748b',
        fontSize: 12,
        rotate: labelRotate,
        interval: 0,
        hideOverlap: true,
      },
    },
    yAxis: {
      type: 'value',
      scale: isLine && categories.length <= 12,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } },
    },
    series: seriesList,
  }
}
