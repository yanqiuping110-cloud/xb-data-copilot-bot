/**
 * 对话 Session API（第 6 周 Agent Memory）。
 */
import request from '../utils/request'

/** 当前用户对话列表 */
export function fetchSessions() {
  return request.get('/api/v1/sessions')
}

/** 创建新对话 */
export function createSession() {
  return request.post('/api/v1/sessions')
}

/** 删除对话 */
export function deleteSession(sessionId) {
  return request.delete(`/api/v1/sessions/${sessionId}`)
}

/** 加载对话消息历史 */
export function fetchSessionMessages(sessionId) {
  return request.get(`/api/v1/sessions/${sessionId}/messages`)
}

/** 用户偏好列表 */
export function fetchPreferences() {
  return request.get('/api/v1/memory/preferences')
}

/** 更新用户偏好 */
export function updatePreferences(preferences) {
  return request.put('/api/v1/memory/preferences', { preferences })
}
