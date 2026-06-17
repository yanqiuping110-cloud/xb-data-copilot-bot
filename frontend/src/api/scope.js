/**
 * DataScope 管理 API（第 13 周 · ADMIN）。
 */
import request from '../utils/request'

/** 已注册范围维度列表 */
export function listScopeDimensions() {
  return request.get('/api/v1/admin/meta/scope-dimensions')
}

/** 注册范围维度 */
export function createScopeDimension(data) {
  return request.post('/api/v1/admin/meta/scope-dimensions', data)
}

/** 表维度列绑定 */
export function getTableScopeBindings(tableId) {
  return request.get(`/api/v1/admin/meta/tables/${tableId}/scope-bindings`)
}

export function putTableScopeBindings(tableId, bindings) {
  return request.put(
    `/api/v1/admin/meta/tables/${tableId}/scope-bindings`,
    bindings.map((b) => ({
      dimension_code: b.dimensionCode,
      column_name: b.columnName,
    })),
  )
}

/** 用户数据授权 */
export function getUserGrants(userId) {
  return request.get(`/api/v1/admin/users/${userId}/grants`)
}

export function putUserDataGrants(userId, grants) {
  return request.put(`/api/v1/admin/users/${userId}/data-grants`, { grants })
}

export function putUserTableGrants(userId, tableNames) {
  return request.put(`/api/v1/admin/users/${userId}/table-grants`, { tableNames })
}

/** 敏感列 deny */
export function listColumnDeny() {
  return request.get('/api/v1/admin/meta/column-deny')
}

export function addColumnDeny(data) {
  return request.post('/api/v1/admin/meta/column-deny', data)
}
