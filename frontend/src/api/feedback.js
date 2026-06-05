/**
 * 问数反馈 API。
 */
import request from '../utils/request'

/** 提交点赞/点踩/badcase */
export function postFeedback(data) {
  return request.post('/api/v1/feedback', data)
}

/** 运营查看 badcase 列表 */
export function listBadcases(params) {
  return request.get('/api/v1/admin/badcases', { params })
}
