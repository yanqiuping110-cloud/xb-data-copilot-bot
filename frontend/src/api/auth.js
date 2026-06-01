/**
 * 认证相关 API（对应 backend /api/v1/auth）。
 */
import request from '../utils/request'

/** 用户名密码登录 */
export function login(data) {
  return request.post('/api/v1/auth/login', data)
}

/** 当前登录用户 */
export function fetchMe() {
  return request.get('/api/v1/auth/me')
}

/** 学校账户切换当前校 */
export function switchSchool(schId) {
  return request.post('/api/v1/auth/switch-school', { schId })
}
