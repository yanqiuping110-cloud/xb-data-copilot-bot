/**
 * Git 代码知识库管理 API（§11.8.5）
 */
import request from '../utils/request'

export function fetchCodeRepos() {
  return request.get('/api/v1/admin/code/repos')
}

export function createCodeRepo(data) {
  return request.post('/api/v1/admin/code/repos', data)
}

export function updateCodeRepo(id, data) {
  return request.put(`/api/v1/admin/code/repos/${id}`, data)
}

export function deleteCodeRepo(id) {
  return request.delete(`/api/v1/admin/code/repos/${id}`)
}

export function syncCodeRepo(id) {
  return request.post(`/api/v1/admin/code/repos/${id}/sync`)
}

export function fetchCodeRepoStatus(id) {
  return request.get(`/api/v1/admin/code/repos/${id}/status`)
}

export function rebuildCodeIndex() {
  return request.post('/api/v1/admin/code/rebuild-index')
}

export function fetchCodeArtifacts(params) {
  return request.get('/api/v1/admin/code/artifacts', { params })
}
