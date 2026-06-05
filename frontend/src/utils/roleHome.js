/**
 * 按角色返回登录后默认首页路径。
 * 超管/运营优先进入元数据表管理；学校账户进入问数页。
 */
export function defaultHomePath(role) {
  if (role === 'ADMIN' || role === 'OPERATOR') {
    return '/admin/meta/tables'
  }
  return '/ask'
}
