/**
 * Insight Engine · 深度分析报告 API
 */
import request from '../utils/request'

const API_BASE = import.meta.env.VITE_API_BASE || ''

export function listResearchReports() {
  return request.get('/api/v1/research/report')
}

export function getResearchReport(reportId) {
  return request.get(`/api/v1/research/report/${reportId}`)
}

export function postResearchReport(data) {
  return request.post('/api/v1/research/report', data)
}

/**
 * SSE 流式生成深度分析报告
 *
 * @param {object} params
 * @param {string} params.requestText
 * @param {string} [params.templateCode]
 * @param {string} [params.sessionId]
 * @param {(evt: object) => void} [params.onEvent] - 原始 SSE 事件 { type, payload }
 * @param {(result: object) => void} [params.onDone]
 * @param {(err: { code: string, message: string }) => void} [params.onError]
 * @param {AbortSignal} [params.signal]
 */
export async function postResearchStream({
  requestText,
  templateCode,
  sessionId,
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

  const url = `${API_BASE}/api/v1/research/report`
  let resp
  try {
    resp = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        requestText,
        templateCode: templateCode || 'monthly_ops',
        sessionId,
        options: { stream: true },
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
    const err = { code: 'NO_STREAM', message: '浏览器不支持流式响应' }
    onError?.(err)
    throw new Error(err.message)
  }

  const decoder = new TextDecoder()
  let buffer = ''

  const dispatch = (block) => {
    const lines = block.split('\n')
    let eventName = 'message'
    let dataLine = ''
    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLine += line.slice(5).trim()
      }
    }
    if (!dataLine) return
    let payload
    try {
      payload = JSON.parse(dataLine)
    } catch {
      return
    }
    onEvent?.({ type: eventName, payload })
    if (eventName === 'report_done') {
      onDone?.(payload)
    } else if (eventName === 'error') {
      onError?.(payload)
    }
  }

  while (true) {
    if (signal?.aborted) {
      throw new DOMException('Aborted', 'AbortError')
    }
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) {
      if (part.trim()) dispatch(part)
    }
  }
  if (buffer.trim()) dispatch(buffer)
}

export function branchResearchReport(reportId, data) {
  return request.post(`/api/v1/research/report/${reportId}/branch`, data)
}

export function getResearchTraces(reportId) {
  return request.get(`/api/v1/research/report/${reportId}/traces`)
}

export function cancelResearchReport(reportId) {
  return request.post(`/api/v1/research/report/${reportId}/cancel`)
}

function authHeaders() {
  const headers = {}
  const token = localStorage.getItem('accessToken')
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

/** 带 JWT 拉取 PDF 二进制（iframe / 下载均须走此接口，不能直接打开 URL） */
export async function fetchResearchPdfBlob(reportId) {
  const url = `${API_BASE}/api/v1/research/report/${reportId}/pdf`
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

export async function downloadResearchPdf(reportId) {
  const blob = await fetchResearchPdfBlob(reportId)
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = `${reportId}.pdf`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}

export async function createResearchPdfObjectUrl(reportId) {
  const blob = await fetchResearchPdfBlob(reportId)
  return URL.createObjectURL(blob)
}
