/**
 * Phase 2 运营 API：术语库、L1 发布、运营统计。
 */
import request from '../utils/request'

export function fetchOpsStats() {
  return request.get('/api/v1/admin/meta/ops/stats')
}

export function listGlossary(params) {
  return request.get('/api/v1/admin/meta/glossary', { params })
}

export function createGlossary(data) {
  return request.post('/api/v1/admin/meta/glossary', data)
}

export function updateGlossary(id, data) {
  return request.put(`/api/v1/admin/meta/glossary/${id}`, data)
}

export function deleteGlossary(id) {
  return request.delete(`/api/v1/admin/meta/glossary/${id}`)
}

export function publishL1Example(id) {
  return request.post(`/api/v1/admin/meta/l1/${id}/publish`)
}

export function promoteGlossaryFromBadcase(traceId) {
  return request.post(`/api/v1/admin/meta/badcase/${traceId}/promote-glossary`)
}

export function promoteL1FromBadcase(traceId) {
  return request.post(`/api/v1/admin/meta/badcase/${traceId}/promote-l1`)
}

export function issueEmbedTokenAdmin(data) {
  return request.post('/api/v1/embed/token/admin', data)
}
