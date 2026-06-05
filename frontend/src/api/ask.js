/**
 * 问数 API（对应 backend POST /api/v1/ask）。
 */
import request from '../utils/request'

const API_BASE = import.meta.env.VITE_API_BASE || ''

/** 提交自然语言问题（一次性 JSON 响应） */
export function postAsk(data) {
  return request.post('/api/v1/ask', data)
}

/**
 * 流式问数：SSE 推送 LangGraph 节点进度与最终结果。
 *
 * @param {object} params
 * @param {string} params.question
 * @param {string} [params.sessionId]
 * @param {(evt: { node: string, label: string, detail?: object }) => void} [params.onProgress]
 * @param {(result: object) => void} [params.onDone]
 * @param {(err: { code: string, message: string }) => void} [params.onError]
 * @param {AbortSignal} [params.signal]
 */
export async function postAskStream({
  question,
  sessionId,
  onProgress,
  onDone,
  onError,
  signal,
}) {
  const token = localStorage.getItem('accessToken')
  const headers = { 'Content-Type': 'application/json' }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const url = `${API_BASE}/api/v1/ask`
  const resp = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      question,
      sessionId,
      options: { stream: true },
    }),
    signal,
  })

  if (!resp.ok) {
    let message = '问数请求失败'
    try {
      const data = await resp.json()
      message = data?.error?.message || message
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
    if (eventName === 'progress') {
      onProgress?.(payload)
    } else if (eventName === 'done') {
      onDone?.(payload)
    } else if (eventName === 'error') {
      onError?.(payload)
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) {
      if (part.trim()) dispatch(part)
    }
  }
  if (buffer.trim()) {
    dispatch(buffer)
  }
}
