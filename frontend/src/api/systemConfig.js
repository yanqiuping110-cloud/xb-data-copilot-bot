/**
 * 系统配置：AI 模型 / 业务数据源 / 系统参数（仅 ADMIN）。
 */
import request from '../utils/request'

export function listLlmProviders() {
  return request.get('/api/v1/admin/system/llm-providers')
}

export function listDatasourceTypes() {
  return request.get('/api/v1/admin/system/datasource-types')
}

export function listLlmModels(params = {}) {
  return request.get('/api/v1/admin/system/llm-models', { params })
}

export function createLlmModel(data) {
  return request.post('/api/v1/admin/system/llm-models', data)
}

export function updateLlmModel(id, data) {
  return request.put(`/api/v1/admin/system/llm-models/${id}`, data)
}

export function deleteLlmModel(id) {
  return request.delete(`/api/v1/admin/system/llm-models/${id}`)
}

export function setDefaultLlmModel(id) {
  return request.post(`/api/v1/admin/system/llm-models/${id}/set-default`)
}

export function testLlmModel(id) {
  return request.post(`/api/v1/admin/system/llm-models/${id}/test`)
}

export function listDatasources() {
  return request.get('/api/v1/admin/system/datasources')
}

export function createDatasource(data) {
  return request.post('/api/v1/admin/system/datasources', data)
}

export function updateDatasource(id, data) {
  return request.put(`/api/v1/admin/system/datasources/${id}`, data)
}

export function deleteDatasource(id) {
  return request.delete(`/api/v1/admin/system/datasources/${id}`)
}

export function setDefaultDatasource(id) {
  return request.post(`/api/v1/admin/system/datasources/${id}/set-default`)
}

export function testDatasourceSaved(id) {
  return request.post(`/api/v1/admin/system/datasources/${id}/test`)
}

export function testDatasourceDraft(data) {
  return request.post('/api/v1/admin/system/datasources/test', data)
}

export function listSysParams() {
  return request.get('/api/v1/admin/system/params')
}

export function updateSysParam(key, value) {
  return request.put(`/api/v1/admin/system/params/${encodeURIComponent(key)}`, { value: String(value) })
}
