/**
 * 问数 API（对应 backend POST /api/v1/ask）。
 */
import request from '../utils/request'

/** 提交自然语言问题 */
export function postAsk(data) {
  return request.post('/api/v1/ask', data)
}
