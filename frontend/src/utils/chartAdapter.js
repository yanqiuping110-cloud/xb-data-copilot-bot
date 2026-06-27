/**
 * 将 columns/rows + chartSpec 转为 ECharts option。
 */

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

  if (chartType === 'pie') {
    const yCol = yCols[0]
    if (!xCol || !yCol) return null
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, type: 'scroll' },
      series: [
        {
          type: 'pie',
          radius: ['36%', '62%'],
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
      tooltip: { trigger: 'item' },
      xAxis: { type: 'value', name: x },
      yAxis: { type: 'value', name: y },
      series: [
        {
          type: 'scatter',
          data: data.map((r) => [numericVal(r[x]), numericVal(r[y])]),
        },
      ],
    }
  }

  const categories = xCol ? data.map((r) => String(r[xCol] ?? '')) : data.map((_, i) => String(i + 1))
  const isLine = chartType === 'line' || chartType === 'area'
  const labelRotate = categories.length > 6 ? 35 : categories.some((c) => c.length > 7) ? 25 : 0
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
      return {
        name: s.name || col,
        type,
        smooth: type === 'line',
        areaStyle: chartType === 'area' && type === 'line' ? {} : undefined,
        data: data.map((r) => numericVal(r[col])),
      }
    },
  )

  return {
    tooltip: { trigger: 'axis' },
    legend: yCols.length > 1 ? { top: 0 } : undefined,
    grid: { left: 52, right: 24, top: yCols.length > 1 ? 36 : 24, bottom: labelRotate > 0 ? 64 : 48 },
    xAxis: {
      type: 'category',
      data: categories,
      boundaryGap: !isLine,
      axisLabel: {
        rotate: labelRotate,
        interval: 0,
        hideOverlap: true,
      },
    },
    yAxis: { type: 'value', scale: isLine && categories.length <= 12 },
    series: seriesList,
  }
}
