/**
 * Axios 封装：统一 baseURL、JWT、错误提示。
 *
 * 本机开发：VITE_API_BASE 留空时走 Vite /api 代理（见 vite.config.js）。
 * 后端错误格式：{ error: { code, message } }
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
  timeout: 120000,
})

// 请求头携带问数自有 JWT（与体育后台 token 无关）
service.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

service.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const data = error.response?.data
    const message = data?.error?.message || error.message || '请求失败'
    if (error.response?.status === 401) {
      localStorage.removeItem('accessToken')
      router.push('/login')
    }
    ElMessage.error(message)
    return Promise.reject(error)
  },
)

export default service
