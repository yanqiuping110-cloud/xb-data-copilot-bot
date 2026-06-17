/**
 * DataScope 授权值解析与展示。
 */

/** 逗号/空格分隔文本 → grant 值数组（按维度 valueType 转型） */
export function parseGrantValues(text, valueType = 'int') {
  return text
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((v) => {
      if (valueType === 'int') {
        const n = Number(v)
        return Number.isNaN(n) ? null : n
      }
      return v
    })
    .filter((v) => v !== null && v !== '')
}

/** grant 对象 → 列表展示摘要 */
export function formatGrantsSummary(dataGrants, dimensions = []) {
  if (!dataGrants || !Object.keys(dataGrants).length) return '—'
  const dimMap = Object.fromEntries(dimensions.map((d) => [d.code, d.display_name || d.code]))
  return Object.entries(dataGrants)
    .map(([code, vals]) => {
      const label = dimMap[code] || code
      const preview = (vals || []).slice(0, 3).join(',')
      const suffix = (vals || []).length > 3 ? '…' : ''
      return `${label}(${preview}${suffix})`
    })
    .join('；')
}
