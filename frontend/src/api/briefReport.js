/**
 * 问数 · 报告分析 API
 */
import request from '../utils/request'

const API_BASE = import.meta.env.VITE_API_BASE || ''

export function fetchBriefReportBackgrounds() {
  return request.get('/api/v1/ask/brief-report/backgrounds')
}

export async function fetchBriefReportBackgroundBlob(path) {
  const url = `${API_BASE}/api/v1/ask/brief-report/backgrounds/file?path=${encodeURIComponent(path)}`
  const resp = await fetch(url, { headers: authHeaders() })
  if (!resp.ok) {
    throw new Error('背景图加载失败')
  }
  return resp.blob()
}

export async function createBriefReportBackgroundObjectUrl(path) {
  const blob = await fetchBriefReportBackgroundBlob(path)
  return URL.createObjectURL(blob)
}

export function listBriefReports() {
  return request.get('/api/v1/ask/brief-report')
}

export function getBriefReport(reportId) {
  return request.get(`/api/v1/ask/brief-report/${reportId}`)
}

export function postBriefReport(data) {
  return request.post('/api/v1/ask/brief-report', data)
}

/**
 * SSE 流式生成报告分析 PDF
 */
export async function postBriefReportStream({
  sessionId,
  traceIds,
  userPrompt,
  options,
  onEvent,
  onDone,
  onError,
  signal,
}) {
  const token = localStorage.getItem('accessToken')
  const headers = { 'Content-Type': 'application/json' }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const url = `${API_BASE}/api/v1/ask/brief-report`
  let resp
  try {
    resp = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        sessionId,
        traceIds,
        userPrompt,
        options: { ...(options || {}), stream: true },
      }),
      signal,
    })
  } catch (err) {
    if (err?.name === 'AbortError') throw err
    const e = { code: 'NETWORK_ERROR', message: err?.message || '报告请求失败' }
    onError?.(e)
    throw err
  }

  if (!resp.ok) {
    let message = '报告请求失败'
    try {
      const data = await resp.json()
      message = data?.error?.message || data?.detail?.error?.message || message
    } catch {
      /* ignore */
    }
    const err = { code: 'HTTP_ERROR', message }
    onError?.(err)
    throw new Error(message)
  }

  const reader = resp.body?.getReader()
  if (!reader) {
    throw new Error('浏览器不支持流式响应')
  }

  const decoder = new TextDecoder()
  let buffer = ''
  let result = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const block of parts) {
      const lines = block.split('\n')
      let eventType = 'message'
      let dataLine = ''
      for (const line of lines) {
        if (line.startsWith('event:')) eventType = line.slice(6).trim()
        if (line.startsWith('data:')) dataLine = line.slice(5).trim()
      }
      if (!dataLine) continue
      let payload
      try {
        payload = JSON.parse(dataLine)
      } catch {
        continue
      }
      onEvent?.({ type: eventType, payload })
      if (eventType === 'report_done') {
        result = payload
      }
      if (eventType === 'error') {
        onError?.({ code: payload.code, message: payload.message })
        throw new Error(payload.message)
      }
    }
  }

  onDone?.(result)
  return result
}

export function briefReportPdfUrl(reportId) {
  const base = API_BASE || ''
  return `${base}/api/v1/ask/brief-report/${reportId}/pdf`
}

function authHeaders() {
  const headers = {}
  const token = localStorage.getItem('accessToken')
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

export async function fetchBriefReportPdfBlob(reportId) {
  const url = briefReportPdfUrl(reportId)
  const resp = await fetch(url, { headers: authHeaders() })
  if (!resp.ok) {
    let message = 'PDF 下载失败'
    try {
      const data = await resp.json()
      message = data?.error?.message || data?.detail?.error?.message || message
    } catch {
      /* ignore */
    }
    throw new Error(message)
  }
  return resp.blob()
}

export async function createBriefReportPdfObjectUrl(reportId) {
  const blob = await fetchBriefReportPdfBlob(reportId)
  return URL.createObjectURL(blob)
}

export async function downloadBriefReportPdf(reportId) {
  const blob = await fetchBriefReportPdfBlob(reportId)
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = `${reportId}.pdf`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}

function parseFilenameFromDisposition(header) {
  if (!header) return null
  const utf8 = header.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1].trim())
    } catch {
      /* ignore */
    }
  }
  const plain = header.match(/filename="?([^";]+)"?/i)
  return plain?.[1] || null
}

export async function downloadBriefReportExcel({ sessionId, traceIds }) {
  const token = localStorage.getItem('accessToken')
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  const url = `${API_BASE}/api/v1/ask/brief-report/export-excel`
  const resp = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({ sessionId, traceIds }),
  })
  if (!resp.ok) {
    let message = 'Excel 导出失败'
    try {
      const data = await resp.json()
      message = data?.error?.message || data?.detail?.error?.message || message
    } catch {
      /* ignore */
    }
    throw new Error(message)
  }
  const blob = await resp.blob()
  const filename =
    parseFilenameFromDisposition(resp.headers.get('Content-Disposition')) || 'ask-export.xlsx'
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}
