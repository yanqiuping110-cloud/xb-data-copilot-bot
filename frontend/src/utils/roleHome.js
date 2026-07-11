/**
 * 按角色返回登录后默认首页路径。
 * 超管进入元数据表管理；运营/渠道进入问数页。
 */
export function defaultHomePath(role) {
  if (role === 'ADMIN') {
    return '/admin/meta/tables'
  }
  return '/ask'
}
