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

/** badcase 一键转为 L1 样例草稿（draft=true，需先填修正 SQL） */
export function draftSqlExampleFromBadcase(traceId) {
  return request.post(`/api/v1/admin/badcases/${traceId}/draft-sql-example`)
}
