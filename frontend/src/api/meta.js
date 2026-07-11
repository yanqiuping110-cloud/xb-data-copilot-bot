/**
 * 元数据 / 语义库管理 API（仅 ADMIN，对应 backend /api/v1/admin/meta）。
 */
import request from '../utils/request'

/** 只读预览业务库表结构（不落库） */
export function introspectTable(tableName) {
  return request.get(`/api/v1/admin/meta/introspect/tables/${encodeURIComponent(tableName)}`)
}

/** 已注册表列表 */
export function listMetaTables(params) {
  return request.get('/api/v1/admin/meta/tables', { params })
}

/** 注册业务表 */
export function createMetaTable(data) {
  return request.post('/api/v1/admin/meta/tables', data)
}

/** 单表详情 */
export function getMetaTable(tableId) {
  return request.get(`/api/v1/admin/meta/tables/${tableId}`)
}

/** 更新表级人工定义 */
export function updateMetaTable(tableId, data) {
  return request.put(`/api/v1/admin/meta/tables/${tableId}`, data)
}

/** 从业务库刷新 auto 字段（保护 manual） */
export function refreshMetaTable(tableId) {
  return request.post(`/api/v1/admin/meta/tables/${tableId}/refresh-from-business`)
}

/** 字段列表 */
export function listMetaColumns(tableId) {
  return request.get(`/api/v1/admin/meta/tables/${tableId}/columns`)
}

/** 更新字段人工定义 */
export function updateMetaColumn(columnId, data) {
  return request.put(`/api/v1/admin/meta/columns/${columnId}`, data)
}

/** 全量重建检索索引 */
export function rebuildMetaIndex() {
  return request.post('/api/v1/admin/meta/rebuild-index')
}

/** 表关系 */
export function listRelations(params) {
  return request.get('/api/v1/admin/meta/relations', { params })
}
export function createRelation(data) {
  return request.post('/api/v1/admin/meta/relations', data)
}
export function updateRelation(id, data) {
  return request.put(`/api/v1/admin/meta/relations/${id}`, data)
}
export function deleteRelation(id) {
  return request.delete(`/api/v1/admin/meta/relations/${id}`)
}

/** 字段取值 */
export function listFieldValues(params) {
  return request.get('/api/v1/admin/meta/field-values', { params })
}
export function createFieldValue(data) {
  return request.post('/api/v1/admin/meta/field-values', data)
}
export function updateFieldValue(id, data) {
  return request.put(`/api/v1/admin/meta/field-values/${id}`, data)
}
export function deleteFieldValue(id) {
  return request.delete(`/api/v1/admin/meta/field-values/${id}`)
}

/** 指标 */
export function listMetrics() {
  return request.get('/api/v1/admin/meta/metrics')
}
export function createMetric(data) {
  return request.post('/api/v1/admin/meta/metrics', data)
}
export function updateMetric(id, data) {
  return request.put(`/api/v1/admin/meta/metrics/${id}`, data)
}
export function deleteMetric(id) {
  return request.delete(`/api/v1/admin/meta/metrics/${id}`)
}

/** L1 样例 SQL */
export function listSqlExamples() {
  return request.get('/api/v1/admin/meta/sql-examples')
}
export function createSqlExample(data) {
  return request.post('/api/v1/admin/meta/sql-examples', data)
}
export function updateSqlExample(id, data) {
  return request.put(`/api/v1/admin/meta/sql-examples/${id}`, data)
}
export function deleteSqlExample(id) {
  return request.delete(`/api/v1/admin/meta/sql-examples/${id}`)
}
