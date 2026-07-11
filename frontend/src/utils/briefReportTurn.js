const EMPTY_ANSWER_RE = /^(\u6839\u636e\u67e5\u8be2\u7ed3\u679c[，,]?\s*)?\u5171\u8fd4\u56de\s*0\s*\u884c/

export function isEmptyAskAnswer(text) {
  return EMPTY_ANSWER_RE.test((text || '').trim())
}

export function turnRowCountFromMessage(msg) {
  const rows = msg?.result?.rows
  if (Array.isArray(rows) && rows.length) return rows.length
  if (typeof msg?.rowCount === 'number') return msg.rowCount
  return 0
}

export function hasReportableContentFromMessage(msg) {
  if (!msg || msg.role !== 'assistant' || msg.isError || !msg.traceId) return false
  const rows = turnRowCountFromMessage(msg)
  const hasChart = Boolean(msg.chartSpec)
  const answer = msg.text || ''
  if (rows > 0) return true
  if (hasChart && !isEmptyAskAnswer(answer)) return true
  return false
}

export function countReportableMessages(messages) {
  return (messages || []).filter((m) => hasReportableContentFromMessage(m)).length
}
