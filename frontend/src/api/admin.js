/**
 * 超管用户管理 API（仅 role=ADMIN，对应 backend /api/v1/admin/users）。
 */
import request from '../utils/request'

/** 分页用户列表 */
export function listUsers(params) {
  return request.get('/api/v1/admin/users', { params })
}

/** 创建运营或学校账户 */
export function createUser(data) {
  return request.post('/api/v1/admin/users', data)
}

/** 禁用/启用、重置密码、改显示名 */
export function patchUser(userId, data) {
  return request.patch(`/api/v1/admin/users/${userId}`, data)
}

/** 学校账户：全量覆盖 sch_id 绑定 */
export function replaceSchools(userId, data) {
  return request.put(`/api/v1/admin/users/${userId}/schools`, data)
}
